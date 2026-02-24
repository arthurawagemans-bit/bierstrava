// BierStrava — Instagram-style Search Page

document.addEventListener('DOMContentLoaded', function() {

    var input = document.getElementById('search-input');
    var clearBtn = document.getElementById('search-clear');
    var results = document.getElementById('search-results');
    if (!input || !results) return;

    var debounceTimer = null;
    var currentQuery = '';

    // ── Init: read ?q= from URL ──
    var initialQ = new URLSearchParams(window.location.search).get('q') || '';
    if (initialQ) {
        input.value = initialQ;
        doSearch(initialQ);
    } else {
        loadSuggestions();
    }
    updateClear();

    // ── Input handler ──
    input.addEventListener('input', function() {
        var q = input.value.trim();
        updateClear();
        clearTimeout(debounceTimer);

        if (!q) {
            currentQuery = '';
            loadSuggestions();
            history.replaceState(null, '', window.location.pathname);
            return;
        }

        debounceTimer = setTimeout(function() { doSearch(q); }, 250);
    });

    // ── Clear button ──
    clearBtn.addEventListener('click', function() {
        input.value = '';
        input.focus();
        currentQuery = '';
        updateClear();
        loadSuggestions();
        history.replaceState(null, '', window.location.pathname);
    });

    function updateClear() {
        clearBtn.classList.toggle('hidden', !input.value);
    }

    // ── Fetch search results ──
    function doSearch(q) {
        currentQuery = q;
        results.innerHTML = spinner();

        fetch('/api/search?q=' + encodeURIComponent(q))
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (currentQuery !== q) return;
                renderResults(data, q);
                history.replaceState(null, '', '?q=' + encodeURIComponent(q));
            })
            .catch(function() {
                results.innerHTML = emptyMsg('Search failed. Try again.');
            });
    }

    // ── Load suggestions ──
    function loadSuggestions() {
        results.innerHTML = spinner();

        fetch('/api/search')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (currentQuery !== '') return;
                renderSuggestions(data);
            })
            .catch(function() {
                results.innerHTML = emptyMsg('Search for users or groups...');
            });
    }

    // ── Render search results ──
    function renderResults(data, q) {
        var html = '';
        var found = false;

        if (data.users && data.users.length) {
            found = true;
            html += sectionHeader('People');
            data.users.forEach(function(u) { html += userCard(u); });
        }

        if (data.groups && data.groups.length) {
            found = true;
            if (data.users && data.users.length) html += '<div class="mt-4"></div>';
            html += sectionHeader('Groups');
            data.groups.forEach(function(g) { html += groupCard(g); });
        }

        if (!found) {
            html = emptyMsg('No results for \u201c' + esc(q) + '\u201d');
        }

        results.innerHTML = html;
    }

    // ── Render suggestions ──
    function renderSuggestions(data) {
        var html = '';

        if (data.users && data.users.length) {
            html += sectionHeader('Suggested');
            data.users.forEach(function(u) { html += userCard(u); });
        }

        if (data.groups && data.groups.length) {
            if (html) html += '<div class="mt-4"></div>';
            html += sectionHeader('Discover Groups');
            data.groups.forEach(function(g) { html += groupCard(g); });
        }

        if (!html) {
            html = emptyMsg('Search for users or groups...');
        }

        results.innerHTML = html;
    }

    // ── User card ──
    function userCard(u) {
        var avatar;
        if (u.avatar) {
            avatar = '<img src="/static/uploads/' + esc(u.avatar) + '" class="w-11 h-11 rounded-full object-cover flex-shrink-0">';
        } else {
            var ch = (u.display_name ? u.display_name[0] : '?').toUpperCase();
            avatar = '<div class="w-11 h-11 rounded-full bg-maroon-100 flex items-center justify-center flex-shrink-0">'
                + '<span class="text-maroon font-bold">' + esc(ch) + '</span></div>';
        }

        var action = '';
        var s = u.connection_status;
        if (s === 'accepted') {
            action = '<span class="text-xs text-gray-400 font-medium flex-shrink-0">Connected</span>';
        } else if (s === 'pending') {
            action = '<span class="text-xs text-maroon-300 font-medium flex-shrink-0">Pending</span>';
        } else if (s === 'incoming_pending') {
            action = '<button class="connect-btn text-xs bg-maroon text-white px-3.5 py-1.5 rounded-full font-medium flex-shrink-0" data-username="' + esc(u.username) + '">Accept</button>';
        } else {
            action = '<button class="connect-btn text-xs bg-maroon text-white px-3.5 py-1.5 rounded-full font-medium flex-shrink-0" data-username="' + esc(u.username) + '">Connect</button>';
        }

        return '<div class="flex items-center gap-3 py-2.5 px-3 bg-white rounded-xl mb-2 border border-gray-100">'
            + '<a href="/u/' + esc(u.username) + '">' + avatar + '</a>'
            + '<a href="/u/' + esc(u.username) + '" class="flex-1 min-w-0">'
            + '<p class="font-semibold text-sm text-gray-900 truncate">' + esc(u.display_name) + '</p>'
            + '<p class="text-xs text-gray-400 truncate">@' + esc(u.username) + '</p>'
            + '</a>'
            + action
            + '</div>';
    }

    // ── Group card ──
    function groupCard(g) {
        var avatar;
        if (g.avatar) {
            avatar = '<img src="/static/uploads/' + esc(g.avatar) + '" class="w-11 h-11 rounded-xl object-cover flex-shrink-0">';
        } else {
            var ch = (g.name ? g.name[0] : '?').toUpperCase();
            avatar = '<div class="w-11 h-11 rounded-xl bg-maroon-100 flex items-center justify-center flex-shrink-0">'
                + '<span class="text-maroon font-bold text-lg">' + esc(ch) + '</span></div>';
        }

        var members = g.member_count + ' member' + (g.member_count !== 1 ? 's' : '');

        var action = '';
        if (g.is_member) {
            action = '<a href="/groups/' + g.id + '" class="text-xs text-gray-400 font-medium flex-shrink-0">Member</a>';
        } else if (g.has_pending_request) {
            action = '<span class="text-xs text-maroon-300 font-medium flex-shrink-0">Requested</span>';
        } else {
            action = '<button class="join-btn text-xs bg-maroon text-white px-3.5 py-1.5 rounded-full font-medium flex-shrink-0" data-group-id="' + g.id + '">Request to Join</button>';
        }

        return '<div class="flex items-center gap-3 py-2.5 px-3 bg-white rounded-xl mb-2 border border-gray-100">'
            + '<a href="/groups/' + g.id + '">' + avatar + '</a>'
            + '<a href="/groups/' + g.id + '" class="flex-1 min-w-0">'
            + '<p class="font-semibold text-sm text-gray-900 truncate">' + esc(g.name) + '</p>'
            + '<p class="text-xs text-gray-400 truncate">' + esc(members) + '</p>'
            + '</a>'
            + action
            + '</div>';
    }

    // ── Delegated click handlers for connect / join ──
    results.addEventListener('click', function(e) {
        var connectBtn = e.target.closest('.connect-btn');
        if (connectBtn) {
            e.preventDefault();
            var username = connectBtn.dataset.username;
            connectBtn.disabled = true;
            connectBtn.textContent = '\u2026';

            ajaxPost('/api/connect/' + username).then(function(data) {
                if (data.success) {
                    if (data.status === 'accepted') {
                        connectBtn.outerHTML = '<span class="text-xs text-gray-400 font-medium flex-shrink-0">Connected</span>';
                    } else {
                        connectBtn.outerHTML = '<span class="text-xs text-maroon-300 font-medium flex-shrink-0">Pending</span>';
                    }
                }
            }).catch(function() {
                connectBtn.disabled = false;
                connectBtn.textContent = 'Connect';
            });
            return;
        }

        var joinBtn = e.target.closest('.join-btn');
        if (joinBtn) {
            e.preventDefault();
            var groupId = joinBtn.dataset.groupId;
            joinBtn.disabled = true;
            joinBtn.textContent = '\u2026';

            ajaxPost('/api/groups/' + groupId + '/join').then(function(data) {
                if (data.success) {
                    joinBtn.outerHTML = '<span class="text-xs text-maroon-300 font-medium flex-shrink-0">Requested</span>';
                } else {
                    joinBtn.disabled = false;
                    joinBtn.textContent = 'Request to Join';
                }
            }).catch(function() {
                joinBtn.disabled = false;
                joinBtn.textContent = 'Request to Join';
            });
            return;
        }
    });

    // ── Helpers ──
    function sectionHeader(text) {
        return '<div class="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-2 px-1">' + esc(text) + '</div>';
    }

    function spinner() {
        return '<div class="flex justify-center py-8"><div class="loading-spinner"></div></div>';
    }

    function emptyMsg(text) {
        return '<div class="text-center py-10"><p class="text-gray-400 text-sm">' + text + '</p></div>';
    }

    function esc(text) {
        if (!text) return '';
        var d = document.createElement('div');
        d.textContent = text;
        return d.innerHTML;
    }
});
