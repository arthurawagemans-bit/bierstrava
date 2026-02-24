// BierStrava - Global JavaScript

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

    // Infinite scroll for feed
    window.setupInfiniteScroll = function(containerSelector, url, pageParam) {
        let currentPage = 1;
        let loading = false;
        let hasMore = true;
        const container = document.querySelector(containerSelector);
        if (!container) return;

        const sentinel = document.createElement('div');
        sentinel.className = 'flex justify-center py-6';
        sentinel.id = 'scroll-sentinel';
        container.after(sentinel);

        const observer = new IntersectionObserver(function(entries) {
            if (entries[0].isIntersecting && !loading && hasMore) {
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
                    sentinel.innerHTML = hasMore ? '' : '<p class="text-gray-400 text-sm">No more posts</p>';
                    loading = false;
                });
            }
        }, { rootMargin: '200px' });

        observer.observe(sentinel);
    };
});
