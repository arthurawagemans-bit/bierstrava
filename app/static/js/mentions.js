// BierStrava — @ Mention Dropdown (people, groups, tags)

document.addEventListener('DOMContentLoaded', function() {

    var debounceTimer = null;
    var activeDropdown = null;
    var activeTextarea = null;
    var mentionStart = -1;
    var selectedIndex = -1;
    var items = [];
    var isSelecting = false;
    var boundEls = new WeakSet();

    function attachMentions(el) {
        if (boundEls.has(el)) return;
        boundEls.add(el);
        el.addEventListener('input', handleInput);
        el.addEventListener('keydown', handleKeydown);
        el.addEventListener('blur', function() {
            setTimeout(function() {
                if (!isSelecting) dismissDropdown();
            }, 200);
        });
    }

    function initMentions() {
        document.querySelectorAll('[data-mentions]').forEach(attachMentions);
    }

    window.initMentions = initMentions;
    initMentions();

    function handleInput(e) {
        var textarea = e.target;
        var value = textarea.value;
        var cursor = textarea.selectionStart;
        var beforeCursor = value.substring(0, cursor);

        // Find the last @ before cursor
        var atIndex = beforeCursor.lastIndexOf('@');
        if (atIndex === -1) { dismissDropdown(); return; }

        // Don't trigger if @ is preceded by a word character (e.g. email)
        if (atIndex > 0 && /\w/.test(value[atIndex - 1])) { dismissDropdown(); return; }

        // Extract query: everything from @ to cursor, but stop at first space
        var raw = beforeCursor.substring(atIndex + 1);
        if (/\s/.test(raw)) { dismissDropdown(); return; }
        if (raw.length < 1) { dismissDropdown(); return; }

        activeTextarea = textarea;
        mentionStart = atIndex;

        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function() {
            fetch('/api/search?q=' + encodeURIComponent(raw))
                .then(function(r) { return r.json(); })
                .then(function(data) { showDropdown(data, textarea); })
                .catch(function(err) { console.error('mentions.js: fetch error', err); dismissDropdown(); });
        }, 200);
    }

    function handleKeydown(e) {
        if (!activeDropdown) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
            highlight();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedIndex = Math.max(selectedIndex - 1, 0);
            highlight();
        } else if (e.key === 'Enter' && selectedIndex >= 0) {
            e.preventDefault();
            selectItem(items[selectedIndex]);
        } else if (e.key === 'Escape') {
            dismissDropdown();
        }
    }

    function showDropdown(data, textarea) {
        // Remove old dropdown DOM without resetting mentionStart/activeTextarea
        // (dismissDropdown resets mentionStart = -1 which breaks selectItem)
        if (activeDropdown) { activeDropdown.remove(); activeDropdown = null; }
        items = [];
        selectedIndex = -1;
        var html = '';

        // People
        if (data.users && data.users.length) {
            html += '<div class="mention-category">People</div>';
            data.users.forEach(function(u) {
                var avatar;
                if (u.avatar) {
                    avatar = '<img src="/static/uploads/' + u.avatar + '" class="mention-avatar">';
                } else {
                    avatar = '<div class="mention-avatar-placeholder">' + (u.display_name[0] || '?').toUpperCase() + '</div>';
                }
                items.push({ value: u.username, display: u.display_name });
                html += '<div class="mention-item" data-index="' + (items.length - 1) + '">'
                    + avatar
                    + '<div class="mention-item-text">'
                    + '<span class="mention-item-name">' + esc(u.display_name) + '</span>'
                    + '<span class="mention-item-sub">@' + esc(u.username) + '</span>'
                    + '</div></div>';
            });
        }

        // Groups
        if (data.groups && data.groups.length) {
            html += '<div class="mention-category">Groups</div>';
            data.groups.forEach(function(g) {
                items.push({ value: g.name.replace(/\s+/g, '_'), display: g.name });
                html += '<div class="mention-item" data-index="' + (items.length - 1) + '">'
                    + '<div class="mention-icon-circle"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/></svg></div>'
                    + '<div class="mention-item-text">'
                    + '<span class="mention-item-name">' + esc(g.name) + '</span>'
                    + '<span class="mention-item-sub">' + g.member_count + ' members</span>'
                    + '</div></div>';
            });
        }

        // Tags (random adds)
        if (data.tags && data.tags.length) {
            html += '<div class="mention-category">Tags</div>';
            data.tags.forEach(function(t) {
                items.push({ value: t.name.replace(/\s+/g, '_'), display: t.name });
                html += '<div class="mention-item" data-index="' + (items.length - 1) + '">'
                    + '<div class="mention-icon-circle"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14"/></svg></div>'
                    + '<div class="mention-item-text">'
                    + '<span class="mention-item-name">' + esc(t.name) + '</span>'
                    + '</div></div>';
            });
        }

        if (!items.length) { dismissDropdown(); return; }

        selectedIndex = 0;
        var dropdown = document.createElement('div');
        dropdown.className = 'mention-dropdown';
        dropdown.innerHTML = html;
        activeDropdown = dropdown;

        // Position below input — use parent container width for small inputs
        var rect = textarea.getBoundingClientRect();
        var parentRect = textarea.closest('.bg-white, .rounded-2xl, form');
        var dropLeft = rect.left;
        var dropWidth = rect.width;
        if (parentRect) {
            var pr = parentRect.getBoundingClientRect();
            dropLeft = pr.left + 16;
            dropWidth = pr.width - 32;
        }
        if (dropWidth < 200) {
            dropLeft = Math.max(8, rect.left - 40);
            dropWidth = Math.min(320, window.innerWidth - 16);
        }

        dropdown.style.position = 'fixed';
        dropdown.style.left = dropLeft + 'px';
        dropdown.style.top = (rect.bottom + 4) + 'px';
        dropdown.style.width = dropWidth + 'px';
        dropdown.style.zIndex = '9999';
        document.body.appendChild(dropdown);
        highlight();

        // Click handlers — mousedown/touchstart fire before blur
        dropdown.querySelectorAll('.mention-item').forEach(function(el) {
            function onSelect(e) {
                e.preventDefault();
                isSelecting = true;
                selectItem(items[parseInt(el.dataset.index)]);
            }
            el.addEventListener('mousedown', onSelect);
            el.addEventListener('touchstart', onSelect, { passive: false });
        });
    }

    function selectItem(item) {
        if (!activeTextarea || mentionStart === -1) return;
        var el = activeTextarea;
        var before = el.value.substring(0, mentionStart);
        var after = el.value.substring(el.selectionStart);
        var insert = '@' + item.value + ' ';
        el.value = before + insert + after;
        el.selectionStart = el.selectionEnd = before.length + insert.length;
        el.focus();
        // Trigger input event so any listeners (e.g. note sync) pick up the change
        el.dispatchEvent(new Event('input', { bubbles: true }));
        isSelecting = false;
        dismissDropdown();
    }

    function highlight() {
        if (!activeDropdown) return;
        activeDropdown.querySelectorAll('.mention-item').forEach(function(el) {
            if (parseInt(el.dataset.index) === selectedIndex) {
                el.classList.add('mention-item-active');
                el.scrollIntoView({ block: 'nearest' });
            } else {
                el.classList.remove('mention-item-active');
            }
        });
    }

    function dismissDropdown() {
        if (activeDropdown) { activeDropdown.remove(); activeDropdown = null; }
        items = [];
        selectedIndex = -1;
        mentionStart = -1;
    }

    function esc(text) {
        var d = document.createElement('div');
        d.textContent = text;
        return d.innerHTML;
    }
});
