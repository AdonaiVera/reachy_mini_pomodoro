/**
 * Reachy Mini Pomodoro - Frontend JavaScript
 */

let appState = {
    timer: {
        state: 'idle',
        time_remaining: 0,
        time_remaining_formatted: '25:00',
        total_pomodoros: 0,
        pomodoros_in_cycle: 0,
        pomodoros_until_long_break: 4,
        current_break_activity: null,
        settings: {
            focus_duration: 1500,
            short_break_duration: 300,
            long_break_duration: 900,
            pomodoros_until_long_break: 4
        }
    },
    tasks: {
        tasks: [],
        current_task_id: null,
        stats: {
            completed_tasks: 0,
            total_pomodoros_today: 0,
            tag_filter: null
        },
        tags: []
    }
};

let selectedPomodoros = 1;
let selectedPriority = 'medium';
let currentTagFilter = null;
let currentDayFilter = '';
let currentPriorityFilter = '';
let updateInterval = null;
let selectedTags = [];
let availableTags = [];
let lastTimerState = 'idle';
let compitaSettings = {
    enabled: true,
    openai_api_key: '',
    voice: 'coral'
};

const elements = {
    timerState: document.getElementById('timer-state'),
    timerDisplay: document.getElementById('timer-display'),
    currentTaskName: document.getElementById('current-task-name'),
    pomodoroDots: document.getElementById('pomodoro-dots'),
    progressLabel: document.getElementById('progress-label'),
    totalPomodoros: document.getElementById('total-pomodoros'),
    completedTasks: document.getElementById('completed-tasks'),
    btnStart: document.getElementById('btn-start'),
    btnPause: document.getElementById('btn-pause'),
    btnResume: document.getElementById('btn-resume'),
    btnStop: document.getElementById('btn-stop'),
    btnSkip: document.getElementById('btn-skip'),
    breakActivityCard: document.getElementById('break-activity-card'),
    activityName: document.getElementById('activity-name'),
    activityDescription: document.getElementById('activity-description'),
    btnDemoActivity: document.getElementById('btn-demo-activity'),
    taskList: document.getElementById('task-list'),
    newTaskTitle: document.getElementById('new-task-title'),
    pomodoroButtons: document.getElementById('pomodoro-buttons'),
    btnAddTask: document.getElementById('btn-add-task'),
    settingsModal: document.getElementById('settings-modal'),
    btnSettings: document.getElementById('btn-settings'),
    btnCloseSettings: document.getElementById('btn-close-settings'),
    btnSaveSettings: document.getElementById('btn-save-settings'),
    btnCelebrate: document.getElementById('btn-celebrate'),
    btnStretch: document.getElementById('btn-stretch'),
    btnBreathe: document.getElementById('btn-breathe'),
    tagFilter: document.getElementById('tag-filter'),
    tagList: document.getElementById('tag-list'),
    tagInput: document.getElementById('tag-input'),
    tagDropdown: document.getElementById('tag-dropdown'),
    selectedTagsContainer: document.getElementById('selected-tags'),
    historyModal: document.getElementById('history-modal'),
    btnHistory: document.getElementById('btn-history'),
    btnCloseHistory: document.getElementById('btn-close-history'),
    historyStats: document.getElementById('history-stats'),
    completedTasksList: document.getElementById('completed-tasks-list'),
    completedTasksSection: document.getElementById('completed-tasks-section'),
    completedTasksHeader: document.getElementById('completed-tasks-header'),
    completedTasksBadge: document.getElementById('completed-tasks-badge'),
    btnCompleteTask: document.getElementById('btn-complete-task'),
    btnAddTag: document.getElementById('btn-add-tag'),
    tagDropdownWrapper: document.getElementById('tag-dropdown-wrapper'),
    newTaskDueDate: document.getElementById('new-task-due-date'),
    priorityButtons: document.getElementById('priority-buttons'),
    dayFilter: document.getElementById('day-filter'),
    priorityFilter: document.getElementById('priority-filter'),
    filtersBar: document.getElementById('filters-bar'),
    compitaEnabled: document.getElementById('compita-enabled'),
    openaiKeyInput: document.getElementById('setting-openai-key'),
    voiceSelect: document.getElementById('setting-voice'),
    btnToggleKey: document.getElementById('btn-toggle-key'),
    compitaStatus: document.getElementById('compita-status'),
    compitaApiKeyGroup: document.getElementById('compita-api-key-group'),
    compitaVoiceGroup: document.getElementById('compita-voice-group')
};

async function apiCall(endpoint, method = 'GET', body = null) {
    try {
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' }
        };
        if (body) {
            options.body = JSON.stringify(body);
        }
        const response = await fetch(`/api${endpoint}`, options);
        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        return null;
    }
}

async function fetchStatus() {
    const data = await apiCall('/status');
    if (data) {
        appState = data;
        updateUI();
    }
}

async function startTimer() {
    const result = await apiCall('/timer/start', 'POST');
    if (result?.success) await fetchStatus();
}

async function pauseTimer() {
    const result = await apiCall('/timer/pause', 'POST');
    if (result?.success) await fetchStatus();
}

async function resumeTimer() {
    const result = await apiCall('/timer/resume', 'POST');
    if (result?.success) await fetchStatus();
}

async function stopTimer() {
    const result = await apiCall('/timer/stop', 'POST');
    if (result?.success) await fetchStatus();
}

async function skipTimer() {
    const result = await apiCall('/timer/skip', 'POST');
    if (result?.success) await fetchStatus();
}

async function addTask() {
    const title = elements.newTaskTitle.value.trim();
    if (!title) return;

    const tags = selectedTags.length > 0 ? selectedTags.map(t => t.name) : null;
    const dueDate = elements.newTaskDueDate.value || null;

    const result = await apiCall('/tasks', 'POST', {
        title,
        estimated_pomodoros: selectedPomodoros,
        tags,
        priority: selectedPriority,
        due_date: dueDate
    });

    if (result?.success) {
        elements.newTaskTitle.value = '';
        elements.tagInput.value = '';
        elements.newTaskDueDate.value = '';
        selectedTags = [];
        renderSelectedTags();
        selectedPomodoros = 1;
        selectedPriority = 'medium';
        updatePomodoroButtons();
        updatePriorityButtons();
        hideTagDropdownWrapper();
        await fetchStatus();
    }
}

function updatePriorityButtons() {
    document.querySelectorAll('.priority-btn').forEach(btn => {
        const value = btn.dataset.value;
        btn.classList.toggle('active', value === selectedPriority);
    });
}

function showTagDropdownWrapper() {
    elements.tagDropdownWrapper.style.display = 'block';
    elements.tagInput.focus();
}

function hideTagDropdownWrapper() {
    elements.tagDropdownWrapper.style.display = 'none';
    elements.tagInput.value = '';
    elements.tagDropdown.classList.remove('visible');
}

async function deleteTask(taskId) {
    const result = await apiCall(`/tasks/${taskId}`, 'DELETE');
    if (result?.success) await fetchStatus();
}

async function selectTask(taskId) {
    const result = await apiCall(`/tasks/${taskId}/select`, 'POST');
    if (result?.success) await fetchStatus();
}

async function completeTask(taskId) {
    const result = await apiCall(`/tasks/${taskId}/complete`, 'POST');
    if (result?.success) await fetchStatus();
}

async function setTagFilter(tag) {
    currentTagFilter = tag;
    if (tag) {
        await apiCall(`/tags/filter?tag=${encodeURIComponent(tag)}`, 'POST');
    } else {
        await apiCall('/tags/filter', 'DELETE');
    }
    await fetchStatus();
}

function renderSelectedTags() {
    elements.selectedTagsContainer.innerHTML = selectedTags.map(tag => `
        <span class="selected-tag" style="background: ${tag.color}" data-tag="${escapeHtml(tag.name)}">
            ${escapeHtml(tag.name)}
            <span class="remove-tag">&times;</span>
        </span>
    `).join('');

    elements.selectedTagsContainer.querySelectorAll('.remove-tag').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const tagName = btn.parentElement.dataset.tag;
            selectedTags = selectedTags.filter(t => t.name !== tagName);
            renderSelectedTags();
        });
    });
}

function showTagDropdown() {
    const inputValue = elements.tagInput.value.trim().toLowerCase();
    availableTags = appState.tasks.tags || [];

    const filteredTags = availableTags.filter(tag =>
        tag.name.toLowerCase().includes(inputValue) &&
        !selectedTags.some(st => st.name === tag.name)
    );

    let html = filteredTags.map(tag => `
        <div class="tag-dropdown-item" data-tag="${escapeHtml(tag.name)}" data-color="${tag.color}">
            <span class="tag-color" style="background: ${tag.color}"></span>
            <span class="tag-name">${escapeHtml(tag.name)}</span>
        </div>
    `).join('');

    if (inputValue && !availableTags.some(t => t.name.toLowerCase() === inputValue)) {
        html += `
            <div class="tag-dropdown-item create-new" data-tag="${escapeHtml(inputValue)}" data-new="true">
                <span class="tag-color"></span>
                <span class="tag-name">Create "${escapeHtml(inputValue)}"</span>
            </div>
        `;
    }

    elements.tagDropdown.innerHTML = html;
    elements.tagDropdown.classList.toggle('visible', html.length > 0);

    elements.tagDropdown.querySelectorAll('.tag-dropdown-item').forEach(item => {
        item.addEventListener('click', async () => {
            const tagName = item.dataset.tag;
            const isNew = item.dataset.new === 'true';
            let tagColor = item.dataset.color;

            if (isNew) {
                const result = await apiCall(`/tags?name=${encodeURIComponent(tagName)}`, 'POST');
                if (result?.success) {
                    tagColor = result.tag.color;
                    await fetchStatus();
                }
            }

            selectedTags.push({ name: tagName, color: tagColor || '#3498db' });
            renderSelectedTags();
            elements.tagInput.value = '';
            elements.tagDropdown.classList.remove('visible');
        });
    });
}

function hideTagDropdown() {
    setTimeout(() => {
        elements.tagDropdown.classList.remove('visible');
    }, 150);
}

function handleTimerStateChange() {
    const currentState = appState.timer.state;
    if (currentState === lastTimerState) return;
    lastTimerState = currentState;
}

async function completeCurrentTask() {
    const taskId = appState.tasks.current_task_id;
    if (!taskId) return;

    await apiCall('/timer/stop', 'POST');
    const result = await apiCall(`/tasks/${taskId}/complete`, 'POST');
    if (result?.success) {
        await fetchStatus();
    }
}

async function fetchHistory() {
    return await apiCall('/history?days=7');
}

async function openHistory() {
    const history = await fetchHistory();
    const stats = await apiCall('/stats');

    if (history && stats) {
        renderHistory(history, stats);
        elements.historyModal.style.display = 'flex';
    }
}

function renderHistory(history, stats) {
    elements.historyStats.innerHTML = `
        <div class="history-stat-card">
            <div class="history-stat-value">${stats.total_pomodoros_today || 0}</div>
            <div class="history-stat-label">Today</div>
        </div>
        <div class="history-stat-card">
            <div class="history-stat-value">${history.total_focus_minutes || 0}</div>
            <div class="history-stat-label">Minutes (7d)</div>
        </div>
    `;

    const completedTasks = appState.tasks.tasks.filter(t => t.status === 'completed');
    elements.completedTasksBadge.textContent = completedTasks.length;

    if (completedTasks.length > 0) {
        const tasksHtml = completedTasks.map(task => {
            const completedDate = task.completed_at
                ? new Date(task.completed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                : '';
            const pomsHtml = Array(task.completed_pomodoros).fill('🍅').join('');
            return `
                <div class="completed-task-item">
                    <span class="task-title">${escapeHtml(task.title)}</span>
                    <span class="task-pomodoros">${pomsHtml}</span>
                    <span class="task-date">${completedDate}</span>
                </div>
            `;
        }).join('');

        elements.completedTasksList.innerHTML = tasksHtml;
        elements.completedTasksSection.style.display = 'block';
    } else {
        elements.completedTasksList.innerHTML = '<p class="history-info">No completed tasks yet</p>';
        elements.completedTasksSection.style.display = 'block';
    }
}

async function saveSettings() {
    const settings = {
        focus_duration: parseInt(document.getElementById('setting-focus').value) * 60,
        short_break_duration: parseInt(document.getElementById('setting-short-break').value) * 60,
        long_break_duration: parseInt(document.getElementById('setting-long-break').value) * 60,
        pomodoros_until_long_break: parseInt(document.getElementById('setting-long-break-interval').value)
    };

    const result = await apiCall('/settings', 'PUT', settings);

    // Save Compita settings
    await saveCompitaSettings();

    if (result?.success) {
        elements.settingsModal.style.display = 'none';
        await fetchStatus();
    }
}

// Compita Settings Functions
async function loadCompitaSettings() {
    const result = await apiCall('/compita/settings');
    if (result) {
        compitaSettings = {
            enabled: result.enabled !== false,
            openai_api_key: result.openai_api_key || '',
            voice: result.voice || 'coral'
        };
        updateCompitaUI();
    }
    await updateCompitaStatus();
}

async function saveCompitaSettings() {
    const newSettings = {
        enabled: elements.compitaEnabled.checked,
        openai_api_key: elements.openaiKeyInput.value.trim(),
        voice: elements.voiceSelect.value
    };

    const wasEnabled = compitaEnabled;
    const result = await apiCall('/compita/settings', 'PUT', newSettings);
    if (result?.success) {
        compitaSettings = newSettings;
        // Store in localStorage as backup
        localStorage.setItem('compitaEnabled', newSettings.enabled ? 'true' : 'false');
        localStorage.setItem('compitaVoice', newSettings.voice);
        // Don't store API key in localStorage for security

        // Handle enabling/disabling voice connection
        if (newSettings.enabled && !wasEnabled) {
            enableVoice();
        } else if (!newSettings.enabled && wasEnabled) {
            stopVoice();
        }
    }
    await updateCompitaStatus();
}

function updateCompitaUI() {
    if (elements.compitaEnabled) {
        elements.compitaEnabled.checked = compitaSettings.enabled;
    }
    if (elements.openaiKeyInput) {
        // Mask the API key if it exists
        elements.openaiKeyInput.value = compitaSettings.openai_api_key ?
            (compitaSettings.openai_api_key.startsWith('sk-') ? compitaSettings.openai_api_key : '••••••••') : '';
    }
    if (elements.voiceSelect) {
        elements.voiceSelect.value = compitaSettings.voice;
    }
    toggleCompitaFields(compitaSettings.enabled);
}

function toggleCompitaFields(enabled) {
    if (elements.compitaApiKeyGroup) {
        elements.compitaApiKeyGroup.style.opacity = enabled ? '1' : '0.5';
        elements.compitaApiKeyGroup.style.pointerEvents = enabled ? 'auto' : 'none';
    }
    if (elements.compitaVoiceGroup) {
        elements.compitaVoiceGroup.style.opacity = enabled ? '1' : '0.5';
        elements.compitaVoiceGroup.style.pointerEvents = enabled ? 'auto' : 'none';
    }
}

async function updateCompitaStatus() {
    const result = await apiCall('/compita/status');
    if (!elements.compitaStatus) return;

    elements.compitaStatus.classList.remove('connected', 'disconnected', 'no-key');
    const statusText = elements.compitaStatus.querySelector('.status-text');

    if (!result) {
        elements.compitaStatus.classList.add('disconnected');
        statusText.textContent = 'Unable to connect';
    } else if (!compitaSettings.enabled) {
        statusText.textContent = 'Disabled';
    } else if (!result.has_api_key) {
        elements.compitaStatus.classList.add('no-key');
        statusText.textContent = 'API key required';
    } else if (result.running) {
        elements.compitaStatus.classList.add('connected');
        statusText.textContent = 'Connected and running';
    } else {
        elements.compitaStatus.classList.add('disconnected');
        statusText.textContent = 'Not running';
    }
}

function toggleApiKeyVisibility() {
    if (!elements.openaiKeyInput || !elements.btnToggleKey) return;

    const isPassword = elements.openaiKeyInput.type === 'password';
    elements.openaiKeyInput.type = isPassword ? 'text' : 'password';
    elements.btnToggleKey.querySelector('.eye-icon').textContent = isPassword ? '🙈' : '👁️';
}

async function openSettings() {
    const settings = appState.timer.settings;
    document.getElementById('setting-focus').value = settings.focus_duration / 60;
    document.getElementById('setting-short-break').value = settings.short_break_duration / 60;
    document.getElementById('setting-long-break').value = settings.long_break_duration / 60;
    document.getElementById('setting-long-break-interval').value = settings.pomodoros_until_long_break;

    // Load Compita settings
    await loadCompitaSettings();

    elements.settingsModal.style.display = 'flex';
}

async function robotCelebrate() {
    await apiCall('/robot/celebrate', 'POST');
}

async function robotStretch() {
    await apiCall('/robot/demo-stretch', 'POST');
}

async function robotBreathe() {
    await apiCall('/robot/demo-breathing', 'POST');
}

async function demoBreakActivity() {
    const activity = appState.timer.current_break_activity;
    if (!activity) return;

    if (activity.name.toLowerCase().includes('breathing')) {
        await robotBreathe();
    } else {
        await robotStretch();
    }
}

function updateUI() {
    handleTimerStateChange();
    updateTimerUI();
    updateTasksUI();
    updateStatsUI();
    updateTagsUI();
}

function updateTimerUI() {
    const { timer } = appState;

    const stateLabels = {
        idle: 'READY',
        focus: 'FOCUS',
        short_break: 'SHORT BREAK',
        long_break: 'LONG BREAK',
        paused: 'PAUSED'
    };
    elements.timerState.textContent = stateLabels[timer.state] || timer.state.toUpperCase();
    elements.timerState.className = `timer-state ${timer.state}`;

    elements.timerDisplay.textContent = timer.time_remaining_formatted;
    elements.timerDisplay.className = `timer-display ${timer.state}`;

    const currentTask = appState.tasks.tasks.find(t => t.id === appState.tasks.current_task_id);
    elements.currentTaskName.textContent = currentTask ? currentTask.title : 'No task selected';

    const dotsHtml = [];
    for (let i = 0; i < timer.settings.pomodoros_until_long_break; i++) {
        const filled = i < timer.pomodoros_in_cycle ? 'filled' : '';
        dotsHtml.push(`<span class="pom-dot ${filled}"></span>`);
    }
    elements.pomodoroDots.innerHTML = dotsHtml.join('');

    const remaining = timer.settings.pomodoros_until_long_break - timer.pomodoros_in_cycle;
    elements.progressLabel.textContent = `${remaining} until long break`;

    const isIdle = timer.state === 'idle';
    const isRunning = ['focus', 'short_break', 'long_break'].includes(timer.state);
    const isPaused = timer.state === 'paused';

    elements.btnStart.style.display = isIdle ? 'inline-flex' : 'none';
    elements.btnPause.style.display = isRunning ? 'inline-flex' : 'none';
    elements.btnResume.style.display = isPaused ? 'inline-flex' : 'none';
    elements.btnStop.style.display = (isRunning || isPaused) ? 'inline-flex' : 'none';
    elements.btnSkip.style.display = isRunning ? 'inline-flex' : 'none';

    const hasCurrentTask = appState.tasks.current_task_id !== null;
    const isFocusing = timer.state === 'focus' || isPaused;
    elements.btnCompleteTask.style.display = (hasCurrentTask && isFocusing) ? 'inline-flex' : 'none';

    if (['short_break', 'long_break'].includes(timer.state) && timer.current_break_activity) {
        elements.breakActivityCard.style.display = 'block';
        elements.activityName.textContent = timer.current_break_activity.name;
        elements.activityDescription.textContent = timer.current_break_activity.description;
        elements.btnDemoActivity.style.display = timer.current_break_activity.robot_demo ? 'inline-flex' : 'none';
    } else {
        elements.breakActivityCard.style.display = 'none';
    }
}

function updateTasksUI() {
    const { tasks, current_task_id } = appState.tasks;

    const allPending = tasks.filter(t => t.status !== 'completed');
    const pendingTasks = filterTasks(allPending);

    elements.taskList.innerHTML = pendingTasks.map(task => renderTask(task, current_task_id)).join('');

    document.querySelectorAll('.task-item').forEach(item => {
        const taskId = item.dataset.taskId;

        item.addEventListener('click', (e) => {
            if (!e.target.closest('.task-checkbox') && !e.target.closest('.task-action-btn')) {
                selectTask(taskId);
            }
        });

        const checkbox = item.querySelector('.task-checkbox');
        if (checkbox) {
            checkbox.addEventListener('click', (e) => {
                e.stopPropagation();
                completeTask(taskId);
            });
        }

        const deleteBtn = item.querySelector('.task-action-btn.delete');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                deleteTask(taskId);
            });
        }
    });
}

function renderTask(task, currentTaskId) {
    const isCurrent = task.id === currentTaskId;
    const isCompleted = task.status === 'completed';

    const tomatoes = [];
    for (let i = 0; i < task.estimated_pomodoros; i++) {
        const filled = i < task.completed_pomodoros ? 'filled' : '';
        tomatoes.push(`<span class="tomato ${filled}">🍅</span>`);
    }

    const tags = task.tags || [];
    const tagsHtml = tags.length > 0
        ? `<div class="task-tags">${tags.map(t => `<span class="task-tag" style="background: ${getTagColor(t)}">${escapeHtml(t)}</span>`).join('')}</div>`
        : '';

    const priority = task.priority || 'medium';
    const priorityHtml = `<span class="task-priority ${priority}">${priority}</span>`;

    let dueDateHtml = '';
    if (task.due_date) {
        const dueClass = getDueDateClass(task.due_date);
        const dueLabel = formatDueDate(task.due_date);
        dueDateHtml = `<span class="task-due ${dueClass}">${dueLabel}</span>`;
    }

    const metaHtml = (priorityHtml || dueDateHtml || tagsHtml)
        ? `<div class="task-meta">${priorityHtml}${dueDateHtml}${tagsHtml}</div>`
        : '';

    return `
        <div class="task-item ${isCurrent ? 'current' : ''} ${isCompleted ? 'completed' : ''}" data-task-id="${task.id}">
            <div class="task-checkbox ${isCompleted ? 'checked' : ''}"></div>
            <div class="task-content">
                <div class="task-title">${escapeHtml(task.title)}</div>
                <div class="task-pomodoros">${tomatoes.join('')}</div>
                ${metaHtml}
            </div>
            <div class="task-actions">
                <button class="task-action-btn delete" title="Delete">🗑️</button>
            </div>
        </div>
    `;
}

function parseDateLocal(dateStr) {
    // Parse ISO date string (YYYY-MM-DD) as local date to avoid timezone issues
    const [year, month, day] = dateStr.split('-').map(Number);
    return new Date(year, month - 1, day);
}

function getToday() {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

function getDueDateClass(dueDateStr) {
    const today = getToday();
    const dueDate = parseDateLocal(dueDateStr);

    if (dueDate < today) return 'overdue';
    if (dueDate.getTime() === today.getTime()) return 'today';
    return '';
}

function formatDueDate(dueDateStr) {
    const today = getToday();
    const dueDate = parseDateLocal(dueDateStr);
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    if (dueDate < today) return 'Overdue';
    if (dueDate.getTime() === today.getTime()) return 'Today';
    if (dueDate.getTime() === tomorrow.getTime()) return 'Tomorrow';

    return dueDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function filterTasks(tasks) {
    return tasks.filter(task => {
        if (currentPriorityFilter && task.priority !== currentPriorityFilter) {
            return false;
        }

        if (currentDayFilter) {
            if (!task.due_date) return false;

            const today = getToday();
            const dueDate = parseDateLocal(task.due_date);
            const tomorrow = new Date(today);
            tomorrow.setDate(tomorrow.getDate() + 1);
            const weekEnd = new Date(today);
            weekEnd.setDate(weekEnd.getDate() + 7);

            switch (currentDayFilter) {
                case 'today':
                    if (dueDate.getTime() !== today.getTime()) return false;
                    break;
                case 'tomorrow':
                    if (dueDate.getTime() !== tomorrow.getTime()) return false;
                    break;
                case 'week':
                    if (dueDate < today || dueDate > weekEnd) return false;
                    break;
                case 'overdue':
                    if (dueDate >= today) return false;
                    break;
            }
        }

        return true;
    });
}

function updateStatsUI() {
    const { stats } = appState.tasks;
    elements.totalPomodoros.textContent = appState.timer.total_pomodoros;
    elements.completedTasks.textContent = stats.completed_tasks;
}

function updateTagsUI() {
    const tags = appState.tasks.tags || [];
    const currentFilter = appState.tasks.stats?.tag_filter || currentTagFilter;

    if (tags.length === 0) {
        elements.tagFilter.classList.remove('has-tags');
        return;
    }

    elements.tagFilter.classList.add('has-tags');

    let tagsHtml = tags.map(tag => {
        const isActive = currentFilter === tag.name.toLowerCase();
        const style = isActive ? `background: ${tag.color}; border-color: ${tag.color};` : '';
        return `<span class="tag-chip ${isActive ? 'active' : ''}" style="${style}" data-tag="${escapeHtml(tag.name)}" data-color="${tag.color}">${escapeHtml(tag.name)}</span>`;
    }).join('');

    if (currentFilter) {
        tagsHtml = `<span class="tag-chip clear" data-tag="">Clear</span>` + tagsHtml;
    }

    elements.tagList.innerHTML = tagsHtml;

    document.querySelectorAll('.tag-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const tag = chip.dataset.tag;
            setTagFilter(tag || null);
        });
    });
}

function getTagColor(tagName) {
    const tags = appState.tasks.tags || [];
    const tag = tags.find(t => t.name.toLowerCase() === tagName.toLowerCase());
    return tag ? tag.color : '#3498db';
}

function updatePomodoroButtons() {
    document.querySelectorAll('.pom-btn').forEach(btn => {
        const value = parseInt(btn.dataset.value);
        btn.classList.toggle('active', value === selectedPomodoros);
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function setupEventListeners() {
    elements.btnStart.addEventListener('click', startTimer);
    elements.btnPause.addEventListener('click', pauseTimer);
    elements.btnResume.addEventListener('click', resumeTimer);
    elements.btnStop.addEventListener('click', stopTimer);
    elements.btnSkip.addEventListener('click', skipTimer);
    elements.btnCompleteTask.addEventListener('click', completeCurrentTask);

    elements.btnAddTask.addEventListener('click', addTask);
    elements.newTaskTitle.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addTask();
    });

    document.querySelectorAll('.pom-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            selectedPomodoros = parseInt(btn.dataset.value);
            updatePomodoroButtons();
        });
    });

    elements.btnSettings.addEventListener('click', openSettings);
    elements.btnCloseSettings.addEventListener('click', () => {
        elements.settingsModal.style.display = 'none';
    });
    elements.btnSaveSettings.addEventListener('click', saveSettings);
    elements.settingsModal.addEventListener('click', (e) => {
        if (e.target === elements.settingsModal) {
            elements.settingsModal.style.display = 'none';
        }
    });

    elements.btnCelebrate.addEventListener('click', robotCelebrate);
    elements.btnStretch.addEventListener('click', robotStretch);
    elements.btnBreathe.addEventListener('click', robotBreathe);
    elements.btnDemoActivity.addEventListener('click', demoBreakActivity);

    elements.btnAddTag.addEventListener('click', () => {
        if (elements.tagDropdownWrapper.style.display === 'none') {
            showTagDropdownWrapper();
        } else {
            hideTagDropdownWrapper();
        }
    });

    elements.tagInput.addEventListener('focus', showTagDropdown);
    elements.tagInput.addEventListener('input', showTagDropdown);
    elements.tagInput.addEventListener('blur', () => {
        hideTagDropdown();
        if (elements.tagInput.value.trim() === '' && selectedTags.length === 0) {
            setTimeout(hideTagDropdownWrapper, 200);
        }
    });

    document.querySelectorAll('.priority-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            selectedPriority = btn.dataset.value;
            updatePriorityButtons();
        });
    });

    elements.dayFilter.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            currentDayFilter = btn.dataset.value;
            elements.dayFilter.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            updateTasksUI();
        });
    });

    elements.priorityFilter.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            currentPriorityFilter = btn.dataset.value;
            elements.priorityFilter.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            updateTasksUI();
        });
    });

    elements.btnHistory.addEventListener('click', openHistory);
    elements.btnCloseHistory.addEventListener('click', () => {
        elements.historyModal.style.display = 'none';
    });
    elements.historyModal.addEventListener('click', (e) => {
        if (e.target === elements.historyModal) {
            elements.historyModal.style.display = 'none';
        }
    });

    elements.completedTasksHeader.addEventListener('click', () => {
        elements.completedTasksSection.classList.toggle('collapsed');
    });

    // Compita settings event listeners
    if (elements.compitaEnabled) {
        elements.compitaEnabled.addEventListener('change', (e) => {
            toggleCompitaFields(e.target.checked);
        });
    }

    if (elements.btnToggleKey) {
        elements.btnToggleKey.addEventListener('click', toggleApiKeyVisibility);
    }
}

async function init() {
    setupEventListeners();
    await fetchStatus();

    if (updateInterval) {
        clearInterval(updateInterval);
    }
    updateInterval = setInterval(fetchStatus, 1000);

    initVoice();
}

// Voice / Compita functionality
const VOICE_SAMPLE_RATE = 24000;
let voiceWs = null;
let voiceAudioContext = null;
let voiceMediaStream = null;
let voiceIsRecording = false;
let voiceRecognition = null;
let voiceRecognitionActive = false;
let voiceAudioQueue = [];
let voiceIsPlaying = false;
let compitaEnabled = true; // Track if Compita should be active

async function initVoice() {
    const voiceIndicator = document.getElementById('voice-indicator');
    const voiceStatus = document.getElementById('voice-status');
    const voiceTranscript = document.getElementById('voice-transcript');

    if (!voiceIndicator) return;

    // Check if Compita is enabled before starting
    try {
        const response = await fetch('/api/compita/status');
        const status = await response.json();
        compitaEnabled = status.enabled !== false;
    } catch (e) {
        console.log('Could not fetch Compita status, defaulting to enabled');
    }

    voiceIndicator.addEventListener('click', () => {
        if (compitaEnabled && (!voiceWs || voiceWs.readyState !== WebSocket.OPEN)) {
            startVoice();
        }
    });

    initVoiceSpeechRecognition();

    if (compitaEnabled) {
        startVoice();
    } else {
        updateVoiceStatus('Compita disabled');
        voiceIndicator.classList.add('disabled');
    }
}

function initVoiceSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        console.log('Speech recognition not supported');
        return;
    }

    voiceRecognition = new SpeechRecognition();
    voiceRecognition.continuous = true;
    voiceRecognition.interimResults = true;
    voiceRecognition.lang = 'en-US';

    voiceRecognition.onresult = (event) => {
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript.toLowerCase();
            console.log('Speech detected:', transcript);
            if (voiceWs && voiceWs.readyState === WebSocket.OPEN) {
                voiceWs.send('transcript:' + transcript);
            }
        }
    };

    voiceRecognition.onerror = (event) => {
        if (event.error === 'no-speech' || event.error === 'aborted') {
            if (voiceRecognitionActive) {
                setTimeout(() => {
                    try { voiceRecognition.start(); } catch (e) {}
                }, 100);
            }
        }
    };

    voiceRecognition.onend = () => {
        if (voiceRecognitionActive) {
            try { voiceRecognition.start(); } catch (e) {}
        }
    };
}

function startVoiceSpeechRecognition() {
    if (voiceRecognition && !voiceRecognitionActive) {
        voiceRecognitionActive = true;
        try { voiceRecognition.start(); } catch (e) {}
    }
}

function stopVoiceSpeechRecognition() {
    voiceRecognitionActive = false;
    if (voiceRecognition) {
        try { voiceRecognition.stop(); } catch (e) {}
    }
}

async function initVoiceAudio() {
    try {
        voiceAudioContext = new AudioContext({ sampleRate: VOICE_SAMPLE_RATE });

        voiceMediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: VOICE_SAMPLE_RATE,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
            }
        });

        const source = voiceAudioContext.createMediaStreamSource(voiceMediaStream);
        const processor = voiceAudioContext.createScriptProcessor(4096, 1, 1);

        processor.onaudioprocess = (e) => {
            if (!voiceIsRecording || !voiceWs || voiceWs.readyState !== WebSocket.OPEN) return;

            const inputData = e.inputBuffer.getChannelData(0);
            let samples = inputData;

            if (voiceAudioContext.sampleRate !== VOICE_SAMPLE_RATE) {
                const ratio = VOICE_SAMPLE_RATE / voiceAudioContext.sampleRate;
                const newLength = Math.round(inputData.length * ratio);
                samples = new Float32Array(newLength);
                for (let i = 0; i < newLength; i++) {
                    const srcIndex = i / ratio;
                    const srcIndexFloor = Math.floor(srcIndex);
                    const srcIndexCeil = Math.min(srcIndexFloor + 1, inputData.length - 1);
                    const t = srcIndex - srcIndexFloor;
                    samples[i] = inputData[srcIndexFloor] * (1 - t) + inputData[srcIndexCeil] * t;
                }
            }

            const pcm16 = new Int16Array(samples.length);
            for (let i = 0; i < samples.length; i++) {
                const s = Math.max(-1, Math.min(1, samples[i]));
                pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }

            voiceWs.send(pcm16.buffer);
        };

        source.connect(processor);
        processor.connect(voiceAudioContext.destination);

    } catch (err) {
        console.error('Failed to init voice audio:', err);
        updateVoiceStatus('Microphone denied');
    }
}

function updateVoiceState(state) {
    const voiceIndicator = document.getElementById('voice-indicator');
    const voiceStatus = document.getElementById('voice-status');
    const voiceTranscript = document.getElementById('voice-transcript');

    if (!voiceIndicator) return;

    voiceIndicator.classList.remove('listening', 'active');

    if (state === 'listening') {
        voiceIndicator.classList.add('listening');
        voiceStatus.textContent = 'Say "Compita"';
    } else if (state === 'active') {
        voiceIndicator.classList.add('active');
        voiceStatus.textContent = 'Listening...';
        voiceTranscript.classList.add('visible');
    } else if (state === 'processing') {
        voiceStatus.textContent = 'Processing...';
    }
}

function updateVoiceStatus(text) {
    const voiceStatus = document.getElementById('voice-status');
    if (voiceStatus) voiceStatus.textContent = text;
}

function addVoiceTranscript(role, text) {
    const voiceTranscript = document.getElementById('voice-transcript');
    if (!voiceTranscript) return;

    const line = document.createElement('div');
    line.className = `voice-transcript-line ${role}`;
    line.innerHTML = `<strong>${role === 'user' ? 'You' : 'Compita'}:</strong> ${text}`;
    voiceTranscript.appendChild(line);
    voiceTranscript.scrollTop = voiceTranscript.scrollHeight;
    voiceTranscript.classList.add('visible');

    setTimeout(() => {
        if (voiceTranscript.children.length > 0) {
            const lastUpdate = voiceTranscript.dataset.lastUpdate;
            if (lastUpdate && Date.now() - parseInt(lastUpdate) > 5000) {
                voiceTranscript.classList.remove('visible');
            }
        }
    }, 8000);
    voiceTranscript.dataset.lastUpdate = Date.now();
}

async function playVoiceAudio(arrayBuffer) {
    if (!voiceAudioContext) return;

    const pcm16 = new Int16Array(arrayBuffer);
    const float32 = new Float32Array(pcm16.length);
    for (let i = 0; i < pcm16.length; i++) {
        float32[i] = pcm16[i] / 32768;
    }

    const audioBuffer = voiceAudioContext.createBuffer(1, float32.length, VOICE_SAMPLE_RATE);
    audioBuffer.getChannelData(0).set(float32);

    voiceAudioQueue.push(audioBuffer);
    if (!voiceIsPlaying) {
        playNextVoiceInQueue();
    }
}

function playNextVoiceInQueue() {
    if (voiceAudioQueue.length === 0) {
        voiceIsPlaying = false;
        return;
    }

    voiceIsPlaying = true;
    const buffer = voiceAudioQueue.shift();
    const source = voiceAudioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(voiceAudioContext.destination);
    source.onended = playNextVoiceInQueue;
    source.start();
}

async function startVoice() {
    await initVoiceAudio();

    if (voiceAudioContext && voiceAudioContext.state === 'suspended') {
        await voiceAudioContext.resume();
    }

    connectVoiceWebSocket();
}

function stopVoice() {
    compitaEnabled = false;
    voiceIsRecording = false;
    stopVoiceSpeechRecognition();

    if (voiceWs) {
        voiceWs.close();
        voiceWs = null;
    }

    if (voiceMediaStream) {
        voiceMediaStream.getTracks().forEach(track => track.stop());
        voiceMediaStream = null;
    }

    const voiceIndicator = document.getElementById('voice-indicator');
    if (voiceIndicator) {
        voiceIndicator.classList.remove('listening', 'active');
        voiceIndicator.classList.add('disabled');
    }
    updateVoiceStatus('Compita disabled');
}

function enableVoice() {
    compitaEnabled = true;
    const voiceIndicator = document.getElementById('voice-indicator');
    if (voiceIndicator) {
        voiceIndicator.classList.remove('disabled');
    }
    startVoice();
}

function connectVoiceWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/compita/stream`;

    voiceWs = new WebSocket(wsUrl);
    voiceWs.binaryType = 'arraybuffer';

    voiceWs.onopen = () => {
        voiceIsRecording = true;
        updateVoiceState('listening');
        startVoiceSpeechRecognition();
        console.log('Voice WebSocket connected');
    };

    voiceWs.onmessage = (event) => {
        if (typeof event.data === 'string') {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'transcript') {
                    addVoiceTranscript(msg.role, msg.text);
                } else if (msg.type === 'state') {
                    updateVoiceState(msg.state);
                }
            } catch (e) {}
        } else {
            playVoiceAudio(event.data);
        }
    };

    voiceWs.onclose = () => {
        voiceIsRecording = false;
        stopVoiceSpeechRecognition();
        if (compitaEnabled) {
            updateVoiceStatus('Disconnected');
            setTimeout(connectVoiceWebSocket, 3000);
        } else {
            updateVoiceStatus('Compita disabled');
        }
    };

    voiceWs.onerror = (err) => {
        console.error('Voice WebSocket error:', err);
    };
}

init();
