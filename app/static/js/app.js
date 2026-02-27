// VEAU - Global JavaScript

// ── Global Modal System ──
var _veauModalResolve = null;

window.veauConfirm = function(msg, okLabel) {
    return new Promise(function(resolve) {
        _veauModalResolve = resolve;
        var modal = document.getElementById('veau-modal');
        var msgEl = document.getElementById('veau-modal-msg');
        var okBtn = document.getElementById('veau-modal-ok');
        msgEl.textContent = msg;
        okBtn.textContent = okLabel || 'Verwijderen';
        modal.classList.remove('hidden');
        okBtn.onclick = function() {
            modal.classList.add('hidden');
            _veauModalResolve = null;
            resolve(true);
        };
    });
};

window.veauModalCancel = function() {
    var modal = document.getElementById('veau-modal');
    modal.classList.add('hidden');
    if (_veauModalResolve) {
        _veauModalResolve(false);
        _veauModalResolve = null;
    }
};

window.veauAlert = function(msg) {
    var toast = document.createElement('div');
    toast.textContent = msg;
    toast.className = 'fixed top-4 left-1/2 -translate-x-1/2 bg-gray-800 text-white text-base px-5 py-3 rounded-xl shadow-lg z-[80] max-w-[90vw] text-center';
    document.body.appendChild(toast);
    setTimeout(function() { toast.remove(); }, 3000);
};

document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss flash messages
    setTimeout(function() {
        const flashes = document.getElementById('flash-messages');
        if (flashes) {
            flashes.remove();
        }
    }, 4000);

    // CSRF token helper for AJAX requests
    window.getCSRFToken = function() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    };

    // Generic AJAX POST helper
    window.ajaxPost = function(url, data) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(data || {})
        }).then(function(response) {
            return response.json();
        });
    };

    // ── Delegated confirm handler for forms with data-confirm ──
    document.addEventListener('submit', function(e) {
        var form = e.target;
        var confirmMsg = form.dataset.confirm;
        if (confirmMsg && !form.dataset.confirmed) {
            e.preventDefault();
            e.stopImmediatePropagation();
            veauConfirm(confirmMsg, form.dataset.confirmOk || 'Verwijderen').then(function(ok) {
                if (ok) {
                    form.dataset.confirmed = 'true';
                    form.requestSubmit();
                }
            });
            return;
        }
        // Prevent double form submissions (existing logic)
        if (form.dataset.submitted) {
            e.preventDefault();
            return;
        }
        form.dataset.submitted = 'true';
        var btn = form.querySelector('button[type="submit"]');
        if (btn) {
            btn.disabled = true;
            btn.style.opacity = '0.6';
        }
    });

    // Like button handler (delegated)
    document.addEventListener('click', function(e) {
        const likeBtn = e.target.closest('.like-btn');
        if (!likeBtn) return;
        e.preventDefault();

        const postId = likeBtn.dataset.postId;
        const countEl = likeBtn.querySelector('.like-count');
        const svgEl = likeBtn.querySelector('svg');

        ajaxPost('/api/posts/' + postId + '/like').then(function(data) {
            if (data.success) {
                countEl.textContent = data.count;
                if (data.liked) {
                    likeBtn.classList.add('liked');
                    svgEl.setAttribute('fill', 'currentColor');
                } else {
                    likeBtn.classList.remove('liked');
                    svgEl.setAttribute('fill', 'none');
                }
            }
        }).catch(function() {
            // Network error — ignore silently
        });
    });

    // Reaction button handler (delegated)
    document.addEventListener('click', function(e) {
        const btn = e.target.closest('.reaction-btn');
        if (!btn) return;
        e.preventDefault();

        const postId = btn.dataset.postId;
        const emoji = btn.dataset.emoji;

        ajaxPost('/api/posts/' + postId + '/reaction', { emoji: emoji }).then(function(data) {
            if (data.success) {
                // Update all reaction buttons for this post
                const container = btn.closest('[data-post-id]');
                if (!container) return;
                container.querySelectorAll('.reaction-btn').forEach(function(b) {
                    const em = b.dataset.emoji;
                    const countEl = b.querySelector('.reaction-count');
                    const count = (data.counts && data.counts[em]) || 0;
                    countEl.textContent = count > 0 ? count : '';
                });
                // Toggle active state for clicked button
                if (data.toggled) {
                    btn.classList.remove('bg-gray-50', 'border-gray-200', 'text-gray-500', 'hover:bg-gray-100');
                    btn.classList.add('bg-maroon-50', 'border-maroon-200', 'text-maroon');
                } else {
                    btn.classList.remove('bg-maroon-50', 'border-maroon-200', 'text-maroon');
                    btn.classList.add('bg-gray-50', 'border-gray-200', 'text-gray-500', 'hover:bg-gray-100');
                }
            }
        }).catch(function() {});
    });

    // Share button handler (delegated)
    document.addEventListener('click', function(e) {
        const btn = e.target.closest('.share-btn');
        if (!btn) return;
        e.preventDefault();

        const url = btn.dataset.postUrl;
        const text = btn.dataset.postText || 'Check out this post on VEAU!';

        if (navigator.share) {
            navigator.share({ title: 'VEAU', text: text, url: url }).catch(function() {});
        } else {
            navigator.clipboard.writeText(url).then(function() {
                veauAlert('Link gekopieerd!');
            }).catch(function() {});
        }
    });

    // WhatsApp share handler (posts + group invites)
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('.wa-share-btn');
        if (btn) {
            e.preventDefault();
            var time = btn.dataset.postTime;
            var user = btn.dataset.postUser;
            var url = btn.dataset.postUrl;
            var msg = time
                ? user + ' dronk ' + time + ' op VEAU! Kun jij dat verslaan? 🍺\n' + url
                : 'Check dit bericht op VEAU! 🍺\n' + url;
            window.open('https://wa.me/?text=' + encodeURIComponent(msg), '_blank');
            return;
        }
        var groupBtn = e.target.closest('#wa-group-btn');
        if (groupBtn) {
            e.preventDefault();
            var name = groupBtn.dataset.groupName;
            var inviteUrl = groupBtn.dataset.inviteUrl;
            var groupMsg = 'Doe mee met ' + name + ' op VEAU! 🍺\n' + inviteUrl;
            window.open('https://wa.me/?text=' + encodeURIComponent(groupMsg), '_blank');
            return;
        }
    });

    // Post menu dropdown (three-dot menu on post cards)
    document.addEventListener('click', function(e) {
        var menuBtn = e.target.closest('.post-menu-btn');
        if (menuBtn) {
            e.preventDefault();
            e.stopPropagation();
            var wrapper = menuBtn.closest('.post-menu-wrapper');
            var dropdown = wrapper.querySelector('.post-menu-dropdown');
            // Close all other open menus first
            document.querySelectorAll('.post-menu-dropdown').forEach(function(d) {
                if (d !== dropdown) d.classList.add('hidden');
            });
            dropdown.classList.toggle('hidden');
            return;
        }
        // Close all menus when clicking elsewhere
        if (!e.target.closest('.post-menu-dropdown')) {
            document.querySelectorAll('.post-menu-dropdown').forEach(function(d) {
                d.classList.add('hidden');
            });
        }
    });

    // Infinite scroll for feed
    window.setupInfiniteScroll = function(containerSelector, url, pageParam) {
        var MAX_PAGES = 50;
        var currentPage = 1;
        var loading = false;
        var hasMore = true;
        var container = document.querySelector(containerSelector);
        if (!container) return;

        var sentinel = document.createElement('div');
        sentinel.className = 'flex justify-center py-6';
        sentinel.id = 'scroll-sentinel';
        container.after(sentinel);

        var observer = new IntersectionObserver(function(entries) {
            if (entries[0].isIntersecting && !loading && hasMore && currentPage < MAX_PAGES) {
                loading = true;
                currentPage++;
                sentinel.innerHTML = '<div class="loading-spinner"></div>';

                fetch(url + '?' + pageParam + '=' + currentPage, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.html && data.html.trim()) {
                        container.insertAdjacentHTML('beforeend', data.html);
                        hasMore = data.has_more;
                    } else {
                        hasMore = false;
                    }
                    if (!hasMore || currentPage >= MAX_PAGES) {
                        sentinel.innerHTML = '<p class="text-gray-400 text-sm">Geen berichten meer</p>';
                        observer.disconnect();
                    } else {
                        sentinel.innerHTML = '';
                    }
                    loading = false;
                })
                .catch(function() {
                    // Network error — allow retry on next scroll
                    loading = false;
                    sentinel.innerHTML = '<p class="text-gray-400 text-sm">Laden mislukt, scroll om opnieuw te proberen</p>';
                });
            }
        }, { rootMargin: '200px' });

        observer.observe(sentinel);
    };
});
