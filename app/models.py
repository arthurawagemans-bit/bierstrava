import logging
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db

logger = logging.getLogger(__name__)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(50), nullable=False)
    bio = db.Column(db.String(300), default='')
    avatar_filename = db.Column(db.String(255), default=None)
    is_private = db.Column(db.Boolean, default=False)
    countdown_enabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship('BeerPost', backref='author', lazy='dynamic',
                            cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='author', lazy='dynamic',
                               cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='user', lazy='dynamic',
                            cascade='all, delete-orphan')
    group_memberships = db.relationship('GroupMember', backref='user', lazy='dynamic',
                                       cascade='all, delete-orphan')
    created_groups = db.relationship('Group', backref='created_by', lazy='select')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def connection_status(self, user):
        """Check outgoing connection status (self → user)."""
        c = Connection.query.filter_by(
            follower_id=self.id, followed_id=user.id
        ).first()
        return c.status if c else None

    def is_accepted_connection_of(self, user):
        return Connection.query.filter(
            db.or_(
                db.and_(Connection.follower_id == self.id, Connection.followed_id == user.id),
                db.and_(Connection.follower_id == user.id, Connection.followed_id == self.id)
            ),
            Connection.status == 'accepted'
        ).first() is not None

    def can_view_profile(self, user):
        if self.id == user.id:
            return True
        if not user.is_private:
            return True
        return self.is_accepted_connection_of(user)

    def connection_count(self):
        return Connection.query.filter_by(
            follower_id=self.id, status='accepted'
        ).count()

    def pending_request_count(self):
        return Connection.query.filter_by(
            followed_id=self.id, status='pending'
        ).count()


class Connection(db.Model):
    """Two-way connection. follower_id=requester, followed_id=addressee.
    Two rows per accepted connection (one per direction).
    Table kept as 'follows' to avoid DB migration."""
    __tablename__ = 'follows'

    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    followed_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    status = db.Column(db.String(10), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    requester = db.relationship('User', foreign_keys=[follower_id],
                                backref=db.backref('outgoing_connections', lazy='dynamic'))
    addressee = db.relationship('User', foreign_keys=[followed_id],
                                backref=db.backref('incoming_connections', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('follower_id', 'followed_id', name='unique_follow'),
        db.Index('idx_connection_follower_status', 'follower_id', 'status'),
        db.Index('idx_connection_followed_status', 'followed_id', 'status'),
    )


class Group(db.Model):
    __tablename__ = 'groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(500), default='')
    avatar_filename = db.Column(db.String(255), default=None)
    invite_code = db.Column(db.String(20), unique=True, nullable=False)
    is_private = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    members = db.relationship('GroupMember', backref='group', lazy='dynamic',
                              cascade='all, delete-orphan')
    post_links = db.relationship('BeerPostGroup', backref='group', lazy='dynamic',
                                 cascade='all, delete-orphan')

    def member_count(self):
        return self.members.count()

    def is_member(self, user):
        return GroupMember.query.filter_by(
            group_id=self.id, user_id=user.id
        ).first() is not None

    def is_admin(self, user):
        m = GroupMember.query.filter_by(
            group_id=self.id, user_id=user.id
        ).first()
        return m and m.role == 'admin'

    def has_pending_request(self, user):
        return GroupJoinRequest.query.filter_by(
            group_id=self.id, user_id=user.id, status='pending'
        ).first() is not None

    def pending_request_count(self):
        return self.join_requests.filter_by(status='pending').count()

    def unseen_post_count(self, user):
        membership = GroupMember.query.filter_by(
            group_id=self.id, user_id=user.id
        ).first()
        if not membership or not membership.last_seen_at:
            return 0
        return db.session.query(BeerPostGroup).join(
            BeerPost, BeerPost.id == BeerPostGroup.post_id
        ).filter(
            BeerPostGroup.group_id == self.id,
            BeerPost.created_at > membership.last_seen_at,
        ).count()


class GroupMember(db.Model):
    __tablename__ = 'group_members'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False, index=True)
    role = db.Column(db.String(10), default='member')
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'group_id', name='unique_membership'),
        db.Index('idx_groupmember_group_user', 'group_id', 'user_id'),
    )


class GroupJoinRequest(db.Model):
    __tablename__ = 'group_join_requests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False, index=True)
    status = db.Column(db.String(10), default='pending')  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('join_requests', lazy='dynamic'))
    group = db.relationship('Group', backref=db.backref('join_requests', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'group_id', name='unique_join_request'),
        db.Index('idx_joinreq_group_status', 'group_id', 'status'),
    )


class Tag(db.Model):
    """Custom @mentions that aren't users or groups.
    Table kept as 'locations' to avoid DB migration."""
    __tablename__ = 'locations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    use_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by = db.relationship('User', backref=db.backref('created_tags', lazy='dynamic'))


class DrinkingSession(db.Model):
    __tablename__ = 'drinking_sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    beers = db.relationship('SessionBeer', backref='session', lazy='select',
                            cascade='all, delete-orphan',
                            order_by='SessionBeer.created_at')

    def beer_count(self):
        return sum(b.beer_count or 1 for b in self.beers)

    def fastest_time(self):
        times = [b.drink_time_seconds for b in self.beers
                 if b.drink_time_seconds is not None]
        return min(times) if times else None

    def vdl_count(self):
        return sum(1 for b in self.beers if b.is_vdl)


class SessionBeer(db.Model):
    __tablename__ = 'session_beers'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('drinking_sessions.id'),
                           nullable=False, index=True)
    drink_time_seconds = db.Column(db.Float, nullable=True)
    is_vdl = db.Column(db.Boolean, default=False)
    beer_count = db.Column(db.Integer, default=1)
    label = db.Column(db.String(50), nullable=True)
    is_pb = db.Column(db.Boolean, default=False)
    pb_rank = db.Column(db.Integer, nullable=True)  # 1=PB, 2=2nd, 3=3rd
    note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BeerPost(db.Model):
    __tablename__ = 'beer_posts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    drink_time_seconds = db.Column(db.Float, nullable=True)
    caption = db.Column('comment', db.String(500), default='')
    photo_filename = db.Column(db.String(255), default=None)
    photo_removed = db.Column(db.Boolean, default=False)
    is_public = db.Column(db.Boolean, default=False)
    is_vdl = db.Column(db.Boolean, default=False)
    beer_count = db.Column(db.Integer, default=1)
    session_id = db.Column(db.Integer, db.ForeignKey('drinking_sessions.id'), nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    session = db.relationship('DrinkingSession', backref='post', lazy='joined')
    location = db.relationship('Tag', backref=db.backref('posts', lazy='dynamic'))
    group_links = db.relationship('BeerPostGroup', backref='post', lazy='select',
                                  cascade='all, delete-orphan')
    _likes = db.relationship('Like', backref='post', lazy='dynamic',
                             cascade='all, delete-orphan')
    _comments = db.relationship('Comment', backref='post', lazy='dynamic',
                                cascade='all, delete-orphan')
    _reactions = db.relationship('Reaction', backref='post', lazy='dynamic',
                                 cascade='all, delete-orphan')

    # Cached counts — set by feed queries to avoid N+1, falls back to DB query
    _like_count = None
    _comment_count = None
    _user_liked = None

    def like_count(self):
        if self._like_count is not None:
            return self._like_count
        return self._likes.count()

    def comment_count(self):
        if self._comment_count is not None:
            return self._comment_count
        return self._comments.count()

    def is_liked_by(self, user):
        if self._user_liked is not None:
            return self._user_liked
        return Like.query.filter_by(
            user_id=user.id, post_id=self.id
        ).first() is not None

    def get_reaction_counts(self):
        """Returns dict like {'fire': 3, 'strong': 1}."""
        rows = db.session.query(
            Reaction.emoji, db.func.count(Reaction.id)
        ).filter(Reaction.post_id == self.id).group_by(Reaction.emoji).all()
        return {emoji: count for emoji, count in rows}

    def user_reactions(self, user):
        """Returns set of emoji slugs this user reacted with."""
        rows = Reaction.query.filter_by(
            user_id=user.id, post_id=self.id
        ).all()
        return {r.emoji for r in rows}

    def visible_to(self, user):
        """Time + caption always visible to connections and group members."""
        if self.user_id == user.id:
            return True
        if user.is_accepted_connection_of(self.author):
            return True
        if not self.author.is_private:
            return True
        my_group_ids = [m.group_id for m in user.group_memberships.all()]
        post_group_ids = [pg.group_id for pg in self.group_links]
        if set(my_group_ids) & set(post_group_ids):
            return True
        return False

    def photo_visible_to(self, user):
        """Photo only visible to selected audiences (connections if is_public, group members)."""
        if not self.photo_filename:
            return False
        return self._photo_shared_with(user)

    def photo_was_shared_with(self, user):
        """True if photo was removed and user would have seen it."""
        if not self.photo_removed:
            return False
        if self.photo_filename:
            return False
        return self._photo_shared_with(user)

    def _photo_shared_with(self, user):
        """Check if user is in the photo's audience (connections if is_public, group members)."""
        if self.user_id == user.id:
            return True
        if self.is_public and user.is_accepted_connection_of(self.author):
            return True
        if self.is_public and not self.author.is_private:
            return True
        my_group_ids = [m.group_id for m in user.group_memberships.all()]
        post_group_ids = [pg.group_id for pg in self.group_links]
        if set(my_group_ids) & set(post_group_ids):
            return True
        return False


    __table_args__ = (
        db.Index('idx_beerpost_user_created', 'user_id', 'created_at'),
    )


class BeerPostGroup(db.Model):
    __tablename__ = 'beer_post_groups'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('beer_posts.id'), nullable=False, index=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False, index=True)

    __table_args__ = (
        db.UniqueConstraint('post_id', 'group_id', name='unique_post_group'),
        db.Index('idx_beerpostgroup_group_post', 'group_id', 'post_id'),
    )


class Like(db.Model):
    __tablename__ = 'likes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey('beer_posts.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'post_id', name='unique_like'),
        db.Index('idx_like_post_user', 'post_id', 'user_id'),
    )


class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey('beer_posts.id'), nullable=False, index=True)
    body = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


ALLOWED_REACTIONS = {'fire', 'strong', 'party', 'laugh'}


class Reaction(db.Model):
    __tablename__ = 'reactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey('beer_posts.id'), nullable=False, index=True)
    emoji = db.Column(db.String(20), nullable=False)  # 'fire', 'strong', 'party', 'laugh'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'post_id', 'emoji', name='unique_reaction'),
        db.Index('idx_reaction_post_emoji', 'post_id', 'emoji'),
    )


class Achievement(db.Model):
    __tablename__ = 'achievements'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(10), nullable=False)
    description = db.Column(db.String(200), nullable=False)


class UserAchievement(db.Model):
    __tablename__ = 'user_achievements'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    achievement_slug = db.Column(db.String(50), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'achievement_slug', name='unique_user_achievement'),
    )


# ---------------------------------------------------------------------------
# Competition (Competitie)
# ---------------------------------------------------------------------------

class Competition(db.Model):
    __tablename__ = 'competitions'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500), default='')
    target_beers = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(15), default='active')  # active, completed
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    group = db.relationship('Group', backref=db.backref('competitions', lazy='dynamic'))
    created_by = db.relationship('User', foreign_keys=[created_by_id],
                                 backref=db.backref('created_competitions', lazy='dynamic'))
    winner = db.relationship('User', foreign_keys=[winner_id],
                             backref=db.backref('won_competitions', lazy='dynamic'))
    participants = db.relationship('CompetitionParticipant', backref='competition',
                                   lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('idx_competition_group_status', 'group_id', 'status'),
    )

    def participant_count(self):
        return self.participants.count()

    def is_participant(self, user):
        return CompetitionParticipant.query.filter_by(
            competition_id=self.id, user_id=user.id
        ).first() is not None

    def leader(self):
        """Return the participant with the most beers."""
        return self.participants.order_by(
            CompetitionParticipant.beer_count.desc()
        ).first()


class CompetitionParticipant(db.Model):
    __tablename__ = 'competition_participants'

    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competitions.id'),
                               nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    beer_count = db.Column(db.Integer, default=0)
    verified_count = db.Column(db.Integer, default=0)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('competition_participations', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('competition_id', 'user_id', name='unique_comp_participant'),
        db.Index('idx_comp_participant_comp_user', 'competition_id', 'user_id'),
    )


class CompetitionBeer(db.Model):
    __tablename__ = 'competition_beers'

    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competitions.id'),
                               nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey('beer_posts.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    beer_count = db.Column(db.Integer, default=1)
    is_verified = db.Column(db.Boolean, default=False)
    verified_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    competition = db.relationship('Competition', backref=db.backref('beers', lazy='dynamic'))
    post = db.relationship('BeerPost', backref=db.backref('competition_beers', lazy='select'))
    user = db.relationship('User', foreign_keys=[user_id])
    verified_by = db.relationship('User', foreign_keys=[verified_by_id])

    __table_args__ = (
        db.UniqueConstraint('competition_id', 'post_id', name='unique_comp_beer'),
        db.Index('idx_comp_beer_comp_user', 'competition_id', 'user_id'),
    )
