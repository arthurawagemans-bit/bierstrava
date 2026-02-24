// Feed page interactions
document.addEventListener('DOMContentLoaded', function() {
    // Set up infinite scroll if feed container exists
    var container = document.getElementById('feed-container');
    if (container && typeof setupInfiniteScroll === 'function') {
        setupInfiniteScroll('#feed-container', '/feed', 'page');
    }
});
