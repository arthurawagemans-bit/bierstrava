// Leaderboard page - horizontal scroll tabs
document.addEventListener('DOMContentLoaded', function() {
    // Scroll active tab into view
    var activeTab = document.querySelector('.bg-maroon.text-white');
    if (activeTab) {
        activeTab.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    }
});
