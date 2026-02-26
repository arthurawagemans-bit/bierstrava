// Post creation — everything is a session
// Flow: Plus → session screen → add beers (timed, VDL, or challenges) → Post Session

document.addEventListener('DOMContentLoaded', function() {

    // ── Hide plus button on create page ──
    var navCreateBtn = document.getElementById('nav-create-btn');
    if (navCreateBtn) navCreateBtn.classList.add('hidden');

    // ── Elements ──
    var timerScreen = document.getElementById('timer-screen');
    var postSection = document.getElementById('post-section');
    var sessionSection = document.getElementById('session-section');
    var display = document.getElementById('stopwatch-display');
    var hint = document.getElementById('timer-hint');
    var resetBtn = document.getElementById('stopwatch-reset');

    // Session elements
    var sessionBeerList = document.getElementById('session-beer-list');
    var sessionTimerBtn = document.getElementById('session-timer-btn');
    var sessionAddVdlBtn = document.getElementById('session-add-vdl-btn');
    var sessionBeersInput = document.getElementById('session-beers-input');
    var sessionActionsEl = document.getElementById('session-actions');

    // Photo elements (session form)
    var sessionPhotoInput = document.getElementById('session-photo-input');
    var sessionPhotoPreview = document.getElementById('session-photo-preview');
    var sessionPhotoPlaceholder = document.getElementById('session-photo-placeholder');

    if (!timerScreen || !display) return;

    // ── Photo preview handler ──
    function setupPhotoPreview(input, preview, placeholder) {
        if (!input) return;
        input.addEventListener('change', function(e) {
            var file = e.target.files[0];
            if (file) {
                var reader = new FileReader();
                reader.onload = function(ev) {
                    preview.src = ev.target.result;
                    preview.classList.remove('hidden');
                    placeholder.classList.add('hidden');
                };
                reader.readAsDataURL(file);
            }
        });
    }

    setupPhotoPreview(sessionPhotoInput, sessionPhotoPreview, sessionPhotoPlaceholder);

    // ── PB value ──
    var pbValue = parseFloat(timerScreen.dataset.pb) || null;

    // ── Countdown preference ──
    var countdownEnabled = timerScreen.dataset.countdown === 'true';

    // ── Countdown State ──
    var countdownActive = false;

    // ── Stopwatch State ──
    var state = 'idle';   // idle | countdown | running | stopped
    var startTime = 0;
    var elapsed = 0;
    var rafId = null;

    // ── Session State ──
    // Each entry: { time, is_vdl, beer_count, label, note }
    var sessionBeers = [];

    // ── Pending timer action ──
    // Set before opening timer, read when timer stops
    var pendingBeerCount = 1;
    var pendingLabel = null;

    var challengeNames = { '2': 'Spies', '4': 'Golden Triangle', '6': 'Kan', '10': 'Platinum Triangle', '12': '1/2 Krat', '24': 'Krat' };

    // ── PB detection ──
    function getPbRank(time, label) {
        if (time === null) return null;
        var key = label || '__bier__';
        var top3 = (window.__topTimes || {})[key] || [];
        var rank = 1;
        for (var i = 0; i < top3.length; i++) {
            if (time >= top3[i]) {
                rank++;
            } else {
                break;
            }
        }
        return rank <= 3 ? rank : null;
    }

    function formatMs(seconds) {
        return seconds.toFixed(3);
    }

    function tick() {
        elapsed = (performance.now() - startTime) / 1000;
        display.textContent = formatMs(elapsed);
        rafId = requestAnimationFrame(tick);
    }

    function vibrate(pattern) {
        if (navigator.vibrate) {
            navigator.vibrate(pattern);
        }
    }

    // ── Countdown then Start ──
    function runCountdown() {
        if (countdownActive) return;
        countdownActive = true;
        state = 'countdown';
        hint.textContent = '';
        hint.classList.add('opacity-50');
        resetBtn.classList.add('hidden');
        display.classList.remove('text-maroon');

        var counts = [3, 2, 1];
        var step = 0;

        function nextStep() {
            if (step < counts.length) {
                display.textContent = counts[step];
                display.classList.remove('text-green-500');
                display.classList.add('text-gray-400');
                display.style.transform = 'scale(1.3)';
                display.style.transition = 'transform 0.3s ease-out';
                setTimeout(function() { display.style.transform = 'scale(1)'; }, 150);
                vibrate(30);
                step++;
                setTimeout(nextStep, 800);
            } else {
                // GO!
                display.textContent = 'GO!';
                display.classList.remove('text-gray-400');
                display.classList.add('text-green-500');
                display.style.transform = 'scale(1.4)';
                setTimeout(function() { display.style.transform = 'scale(1)'; }, 200);
                vibrate([50, 30, 50]);
                setTimeout(function() {
                    display.classList.remove('text-green-500');
                    countdownActive = false;
                    startTimerNow();
                }, 500);
            }
        }
        nextStep();
    }

    function startTimerNow() {
        state = 'running';
        startTime = performance.now();
        elapsed = 0;

        hint.textContent = 'Tap anywhere to stop';
        hint.classList.add('opacity-50');
        resetBtn.classList.add('hidden');

        display.classList.remove('text-maroon');
        display.classList.add('text-red-600', 'stopwatch-running');
        timerScreen.classList.add('bg-gray-100');
        timerScreen.classList.remove('bg-gray-50');

        vibrate(50);
        tick();
    }

    // ── Stop ──
    function stopTimer() {
        state = 'stopped';
        cancelAnimationFrame(rafId);
        elapsed = (performance.now() - startTime) / 1000;
        display.textContent = formatMs(elapsed);

        hint.textContent = 'Tap to time another';
        hint.classList.remove('opacity-50');
        resetBtn.classList.remove('hidden');

        display.classList.remove('text-red-600', 'stopwatch-running');
        display.classList.add('text-maroon');
        timerScreen.classList.remove('bg-gray-100');
        timerScreen.classList.add('bg-gray-50');

        vibrate([50, 30, 50]);

        // Add entry to session after short delay
        setTimeout(function() {
            var pbRank = getPbRank(elapsed, pendingLabel);
            sessionBeers.push({
                time: elapsed,
                is_vdl: false,
                beer_count: pendingBeerCount,
                label: pendingLabel,
                note: '',
                pb_rank: pbRank
            });
            // Reset pending
            pendingBeerCount = 1;
            pendingLabel = null;
            showSessionForm();
        }, 500);
    }

    // ── Reset ──
    function resetTimer() {
        state = 'idle';
        cancelAnimationFrame(rafId);
        elapsed = 0;
        display.textContent = '0.000';
        display.style.transform = '';
        display.style.transition = '';
        hint.textContent = countdownEnabled ? 'Tap to start countdown' : 'Tap anywhere to start';
        hint.classList.remove('opacity-50');
        display.classList.remove('text-red-600', 'stopwatch-running');
        display.classList.add('text-maroon');
        timerScreen.classList.remove('bg-gray-100');
        timerScreen.classList.add('bg-gray-50');
        resetBtn.classList.add('hidden');
    }

    // ── Hide all sections ──
    function hideAll() {
        timerScreen.classList.add('hidden');
        if (postSection) postSection.classList.add('hidden');
        if (sessionSection) sessionSection.classList.add('hidden');
        var preview = document.getElementById('preview-section');
        if (preview) preview.classList.add('hidden');
    }

    // ── Show Timer Screen ──
    function showTimerScreen() {
        hideAll();
        timerScreen.classList.remove('hidden');
        resetTimer();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ── Show Session Form ──
    function showSessionForm() {
        hideAll();
        sessionSection.classList.remove('hidden');
        sessionSection.style.animation = 'fadeIn 0.3s ease-out';
        renderSessionBeerList();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ── Render session beer list ──
    function renderSessionBeerList() {
        if (!sessionBeerList) return;

        // Calculate total beers
        var totalBeers = 0;
        sessionBeers.forEach(function(b) { totalBeers += (b.beer_count || 1); });

        // Find fastest timed entry (per-beer time for comparison)
        var fastestTime = null;
        sessionBeers.forEach(function(b) {
            if (!b.is_vdl && b.time !== null) {
                if (fastestTime === null || b.time < fastestTime) {
                    fastestTime = b.time;
                }
            }
        });

        var html = '';
        sessionBeers.forEach(function(beer, i) {
            var isFastest = !beer.is_vdl && beer.time !== null && beer.time === fastestTime;
            var entryLabel;
            var displayText;
            var cls;

            if (beer.is_vdl) {
                entryLabel = 'VDL';
                displayText = '1 bier';
                cls = 'bg-amber-100 text-amber-700';
            } else if (beer.label) {
                entryLabel = beer.label;
                displayText = formatMs(beer.time) + 's';
                cls = isFastest ? 'time-badge' : 'bg-gray-100 text-gray-600';
            } else {
                entryLabel = 'Bier';
                displayText = formatMs(beer.time) + 's';
                cls = isFastest ? 'time-badge' : 'bg-gray-100 text-gray-600';
            }

            var noteVal = beer.note || '';

            html += '<div class="flex items-center justify-between py-2 ' +
                    (i > 0 ? 'border-t border-gray-50' : '') + '">';
            // Left: label + note input
            html += '<div class="flex items-center gap-2 flex-1 min-w-0">';
            html += '<span class="text-sm text-gray-700 font-medium flex-shrink-0">' + entryLabel + '</span>';
            if (beer.pb_rank === 1) {
                html += '<span class="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-green-100 text-green-700 flex-shrink-0">PB!</span>';
            } else if (beer.pb_rank === 2) {
                html += '<span class="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-600 flex-shrink-0">2nd</span>';
            } else if (beer.pb_rank === 3) {
                html += '<span class="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-500 flex-shrink-0">3rd</span>';
            }
            if (beer.beer_count > 1) {
                html += '<span class="text-[11px] text-gray-400 flex-shrink-0">(' + beer.beer_count + ')</span>';
            }
            html += '<input type="text" data-mentions data-note-index="' + i + '" maxlength="200" ' +
                    'class="session-note-input flex-1 min-w-0 text-xs text-gray-500 bg-transparent border-0 p-0 focus:ring-0 focus:outline-none placeholder-gray-300" ' +
                    'placeholder="@ tag" value="' + noteVal.replace(/"/g, '&quot;') + '">';
            html += '</div>';
            // Right: time + remove
            html += '<div class="flex items-center gap-2 flex-shrink-0">';
            html += '<span class="text-xs font-bold px-2.5 py-1 rounded-full ' + cls + '">' + displayText + '</span>';
            html += '<button type="button" class="text-gray-300 hover:text-red-400 text-lg leading-none session-remove-beer" data-index="' + i + '">&times;</button>';
            html += '</div></div>';
        });

        sessionBeerList.innerHTML = html;

        // Attach remove handlers
        document.querySelectorAll('.session-remove-beer').forEach(function(btn) {
            btn.addEventListener('click', function() {
                sessionBeers.splice(parseInt(this.dataset.index), 1);
                renderSessionBeerList();
            });
        });

        // Attach note input handlers
        document.querySelectorAll('.session-note-input').forEach(function(input) {
            input.addEventListener('input', function() {
                var idx = parseInt(this.dataset.noteIndex);
                sessionBeers[idx].note = this.value;
                // Update hidden input live (no re-render to keep focus)
                if (sessionBeersInput) {
                    sessionBeersInput.value = JSON.stringify(sessionBeers);
                }
            });
        });

        // Re-initialize mentions on new inputs
        if (window.initMentions) {
            window.initMentions();
        }

        // Update hidden input
        if (sessionBeersInput) {
            sessionBeersInput.value = JSON.stringify(sessionBeers);
        }

        // Update beer count display
        var countEl = document.getElementById('session-beer-count');
        if (countEl) {
            countEl.textContent = totalBeers + ' bier' + (totalBeers !== 1 ? 's' : '');
        }
    }

    // ── Timer screen tap handler ──
    timerScreen.addEventListener('click', function(e) {
        if (e.target.closest('#stopwatch-reset')) return;

        if (state === 'idle') {
            if (countdownEnabled) {
                runCountdown();
            } else {
                startTimerNow();
            }
        } else if (state === 'countdown') {
            // Ignore taps during countdown
            return;
        } else if (state === 'running') {
            stopTimer();
        } else if (state === 'stopped') {
            if (countdownEnabled) {
                runCountdown();
            } else {
                startTimerNow();
            }
        }
    });

    resetBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        resetTimer();
    });

    // ── Beer (timed) button ──
    if (sessionTimerBtn) {
        sessionTimerBtn.addEventListener('click', function() {
            pendingBeerCount = 1;
            pendingLabel = null;
            showTimerScreen();
        });
    }

    // ── VDL button ──
    if (sessionAddVdlBtn) {
        sessionAddVdlBtn.addEventListener('click', function() {
            sessionBeers.push({ time: null, is_vdl: true, beer_count: 1, label: null, note: '' });
            renderSessionBeerList();
        });
    }

    // ── Challenge buttons ──
    document.querySelectorAll('.session-challenge-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var beers = parseInt(this.dataset.beers);
            pendingBeerCount = beers;
            pendingLabel = challengeNames[beers] || (beers + ' biers');
            showTimerScreen();
        });
    });

    // ── Preview ──
    var previewSection = document.getElementById('preview-section');
    var previewBtn = document.getElementById('preview-session-btn');
    var previewBackBtn = document.getElementById('preview-back-btn');
    var previewEditBtn = document.getElementById('preview-edit-btn');

    function showPreview() {
        // Sync session data to hidden input before preview
        if (sessionBeersInput) {
            sessionBeersInput.value = JSON.stringify(sessionBeers);
        }

        hideAll();
        previewSection.classList.remove('hidden');
        previewSection.style.animation = 'fadeIn 0.3s ease-out';
        window.scrollTo({ top: 0, behavior: 'smooth' });

        // Build time bar
        var timeBar = document.getElementById('preview-time-bar');
        var html = '<div class="space-y-1.5">';

        var totalBeers = 0;
        sessionBeers.forEach(function(beer) {
            totalBeers += (beer.beer_count || 1);
            var label = beer.label || 'Bier';
            html += '<div class="flex items-center justify-between">';
            html += '<div class="flex items-center gap-1.5 flex-1 min-w-0">';
            html += '<span class="text-sm font-medium text-gray-700 flex-shrink-0">' + label + '</span>';
            if (beer.pb_rank === 1) {
                html += '<span class="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-green-100 text-green-700 flex-shrink-0">PB!</span>';
            } else if (beer.pb_rank === 2) {
                html += '<span class="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-600 flex-shrink-0">2nd</span>';
            } else if (beer.pb_rank === 3) {
                html += '<span class="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-500 flex-shrink-0">3rd</span>';
            }
            if (beer.beer_count && beer.beer_count > 1) {
                html += '<span class="text-[11px] text-gray-400 flex-shrink-0">(' + beer.beer_count + ')</span>';
            }
            if (beer.note) {
                html += '<span class="text-[11px] text-gray-400 truncate">' + escapeHtml(beer.note) + '</span>';
            }
            html += '</div>';
            if (beer.is_vdl) {
                html += '<span class="text-xs font-bold px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-700 flex-shrink-0">VDL</span>';
            } else if (beer.time !== null) {
                html += '<span class="time-badge text-xs font-bold px-2.5 py-0.5 rounded-full flex-shrink-0">' + formatMs(beer.time) + 's</span>';
            }
            html += '</div>';
        });

        html += '<div class="flex items-center justify-between pt-1.5 border-t border-gray-200">';
        html += '<span class="text-xs font-semibold text-gray-500">Session total</span>';
        html += '<span class="text-xs font-bold text-maroon">' + totalBeers + ' bier' + (totalBeers !== 1 ? 's' : '') + '</span>';
        html += '</div></div>';
        timeBar.innerHTML = html;

        // Caption
        var captionEl = document.getElementById('preview-caption');
        var sessionForm = document.getElementById('session-form');
        var captionInput = sessionForm.querySelector('textarea[name="caption"]');
        var captionText = captionInput ? captionInput.value.trim() : '';
        if (captionText) {
            captionEl.textContent = captionText;
            captionEl.classList.remove('hidden');
        } else {
            captionEl.classList.add('hidden');
        }

        // Photo
        var photoContainer = document.getElementById('preview-photo-container');
        var previewPhotoImg = document.getElementById('preview-photo');
        var srcPhoto = document.getElementById('session-photo-preview');
        if (srcPhoto && !srcPhoto.classList.contains('hidden') && srcPhoto.src) {
            previewPhotoImg.src = srcPhoto.src;
            photoContainer.classList.remove('hidden');
        } else {
            photoContainer.classList.add('hidden');
        }

        // Sharing info
        var shareList = document.getElementById('preview-share-list');
        var shares = [];
        var publicCheckbox = sessionForm.querySelector('input[name="is_public"]');
        if (publicCheckbox && publicCheckbox.checked) {
            shares.push('Your connections');
        }
        sessionForm.querySelectorAll('input[name="groups"]:checked').forEach(function(cb) {
            var label = cb.closest('label');
            if (label) {
                shares.push(label.querySelector('span').textContent.trim());
            }
        });
        shareList.textContent = shares.length ? shares.join(', ') : 'No one (private)';
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    if (previewBtn) {
        previewBtn.addEventListener('click', function() {
            if (sessionBeers.length < 1) {
                alert('Add at least one bier to your session first.');
                return;
            }
            showPreview();
        });
    }

    if (previewBackBtn) {
        previewBackBtn.addEventListener('click', showSessionForm);
    }
    if (previewEditBtn) {
        previewEditBtn.addEventListener('click', showSessionForm);
    }

    // ── Initial render ──
    renderSessionBeerList();
});
