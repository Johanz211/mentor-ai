/* ═══════════════════════════════════════════
   Mentor AI — Frontend Logic
   ═══════════════════════════════════════════ */

const state = {
    mentor: "embedded",
    streaming: false,
    files: [],
};

// Markdown renderer config (safe init — CDN might be slow)
try {
    if (typeof marked !== "undefined") {
        marked.setOptions({
            highlight: (code, lang) => {
                if (typeof hljs !== "undefined" && lang && hljs.getLanguage(lang)) {
                    return hljs.highlight(code, { language: lang }).value;
                }
                if (typeof hljs !== "undefined") return hljs.highlightAuto(code).value;
                return code;
            },
            breaks: true,
        });
    }
} catch (e) { console.warn("marked init deferred:", e); }

// Quick-start questions per mentor
const QUICK_STARTS = {
    embedded: [
        "What is 0xFF in binary?",
        "How does the CAN bus work?",
        "Explain STM32 GPIO setup",
        "What is a volatile keyword in C?",
        "How to set up a timer interrupt?",
    ],
    qa: [
        "Explain the test pyramid",
        "How to write a Page Object Model?",
        "What is API contract testing?",
        "Best CI/CD pipeline for tests?",
        "How to handle flaky tests?",
    ],
    leetcode: [
        "Explain the sliding window pattern",
        "How does binary search work?",
        "When to use DFS vs BFS?",
        "What is dynamic programming?",
        "Two sum — walk me through it",
    ],
    mechanical: [
        "Explain Mohr's circle",
        "What is the Carnot cycle?",
        "How do gears transmit power?",
        "Bernoulli's equation explained",
        "What is GD&T?",
    ],
    vcs: [
        "Explain git rebase vs merge",
        "What is a detached HEAD?",
        "How does Git store data internally?",
        "Best branching strategy for small teams?",
        "How to undo a bad commit?",
    ],
};


// ── Init ──

async function init() {
    await loadMentors();
    await loadFiles();
    await loadHistory(state.mentor);
}

async function loadMentors() {
    try {
        const resp = await fetch("/api/mentors");
        const mentors = await resp.json();
        const list = document.getElementById("mentor-list");
        list.innerHTML = "";

        for (const [key, m] of Object.entries(mentors)) {
            const card = document.createElement("div");
            card.className = `mentor-card${key === state.mentor ? " active" : ""}`;
            card.dataset.key = key;
            card.innerHTML = `
                <div class="icon">${m.icon}</div>
                <div class="info">
                    <div class="name">${m.name}</div>
                    <div class="desc">${m.description}</div>
                </div>
            `;
            card.onclick = () => selectMentor(key, m);
            list.appendChild(card);
        }

        // Set initial header
        const initial = mentors[state.mentor];
        if (initial) {
            document.getElementById("current-mentor-icon").textContent = initial.icon;
            document.getElementById("current-mentor-name").textContent = initial.name;
            renderQuickStarts(state.mentor);
        }
    } catch (e) {
        console.error("Failed to load mentors:", e);
    }
}

function selectMentor(key, m) {
    const previous = state.mentor;
    state.mentor = key;

    document.querySelectorAll(".mentor-card").forEach(c => c.classList.remove("active"));
    document.querySelector(`.mentor-card[data-key="${key}"]`).classList.add("active");

    document.getElementById("current-mentor-icon").textContent = m.icon;
    document.getElementById("current-mentor-name").textContent = m.name;

    // Reload files for this mentor
    loadFiles();

    // Load persisted history for this mentor
    if (previous !== key) {
        loadHistory(key);
    }
}

async function loadHistory(mentorKey) {
    try {
        const resp = await fetch(`/api/history/${mentorKey}`);
        const data = await resp.json();
        const messages = document.getElementById("messages");

        if (data.messages && data.messages.length > 0) {
            // Has history — render it
            messages.innerHTML = "";
            for (const msg of data.messages) {
                addMessage(msg.role, msg.role === "user" ? msg.content :
                    (typeof marked !== "undefined" ? marked.parse(msg.content) : msg.content));
            }
            addSystemMessage(`📜 ${data.total} messages restored`);
        } else {
            // No history — show welcome
            messages.innerHTML = `
                <div class="welcome-message" id="welcome">
                    <div class="welcome-icon">🎓</div>
                    <h2>Welcome to Mentor AI</h2>
                    <p>Pick a mentor from the sidebar and ask anything.<br>Upload code files for context-aware help.</p>
                    <div class="quick-starts" id="quick-starts"></div>
                </div>
            `;
            renderQuickStarts(mentorKey);
        }
    } catch (e) {
        console.error("Failed to load history:", e);
    }
}

function renderQuickStarts(mentorKey) {
    const container = document.getElementById("quick-starts");
    if (!container) return;

    const questions = QUICK_STARTS[mentorKey] || [];
    container.innerHTML = questions.map(q =>
        `<button class="quick-start-btn" onclick="sendQuickStart('${q.replace(/'/g, "\\'")}')">${q}</button>`
    ).join("");
}

function sendQuickStart(text) {
    document.getElementById("message-input").value = text;
    sendMessage();
}


// ── Files ──

async function loadFiles() {
    try {
        const resp = await fetch(`/api/files?mentor=${state.mentor}`);
        state.files = await resp.json();
        renderFiles();
    } catch (e) {
        console.error("Failed to load files:", e);
    }
}

function renderFiles() {
    const list = document.getElementById("file-list");
    const count = document.getElementById("file-count");

    count.textContent = state.files.length || "";

    list.innerHTML = state.files.map(f => `
        <div class="file-item">
            <span class="name">📄 ${f.name}</span>
            <span class="small">${formatSize(f.size)}</span>
            <button class="delete-btn" onclick="deleteFile('${f.id}')" title="Remove">✕</button>
        </div>
    `).join("");
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + "B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + "KB";
    return (bytes / (1024 * 1024)).toFixed(1) + "MB";
}

async function uploadFile(file) {
    const form = new FormData();
    form.append("file", file);
    form.append("mentor", state.mentor);
    try {
        const resp = await fetch("/api/upload", { method: "POST", body: form });
        const data = await resp.json();
        state.files.push(data);
        renderFiles();
    } catch (e) {
        console.error("Upload failed:", e);
    }
}

async function deleteFile(id) {
    try {
        await fetch(`/api/files/${id}`, { method: "DELETE" });
        state.files = state.files.filter(f => f.id !== id);
        renderFiles();
    } catch (e) {
        console.error("Delete failed:", e);
    }
}

// ── Drag & drop (deferred to DOMContentLoaded) ──

document.addEventListener("DOMContentLoaded", () => {
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });
    dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
        for (const file of e.dataTransfer.files) uploadFile(file);
    });
    fileInput.addEventListener("change", () => {
        for (const file of fileInput.files) uploadFile(file);
        fileInput.value = "";
    });

    const textarea = document.getElementById("message-input");
    textarea.addEventListener("input", () => {
        textarea.style.height = "auto";
        textarea.style.height = Math.min(textarea.scrollHeight, 150) + "px";
    });
    textarea.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    init();
});


// ── Chat ──

async function sendMessage() {
    const input = document.getElementById("message-input");
    const text = input.value.trim();
    if (!text || state.streaming) return;

    input.value = "";
    input.style.height = "auto";

    // Remove welcome screen
    const welcome = document.getElementById("welcome");
    if (welcome) welcome.remove();

    // Add user message
    addMessage("user", text);

    // Create assistant message placeholder
    const msgEl = addMessage("assistant", "");
    const contentEl = msgEl.querySelector(".message-content");
    contentEl.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';

    state.streaming = true;
    document.getElementById("send-btn").disabled = true;

    try {
        const resp = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                mentor: state.mentor,
                message: text,
            }),
        });

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let fullText = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split("\n");

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.token) {
                        fullText += data.token;
                        contentEl.innerHTML = marked.parse(fullText);
                        // Highlight code blocks
                        contentEl.querySelectorAll("pre code:not(.hljs)").forEach(el => {
                            hljs.highlightElement(el);
                        });
                        scrollToBottom();
                    }
                    if (data.error) {
                        contentEl.innerHTML = `<span style="color:var(--red)">❌ ${data.error}</span>`;
                    }
                } catch (e) { /* skip malformed lines */ }
            }
        }
    } catch (e) {
        contentEl.innerHTML = `<span style="color:var(--red)">❌ Connection error: ${e.message}</span>`;
    }

    state.streaming = false;
    document.getElementById("send-btn").disabled = false;
    document.getElementById("message-input").focus();
}

function addMessage(role, text) {
    const messages = document.getElementById("messages");
    const div = document.createElement("div");
    div.className = `message ${role}`;

    const label = role === "user" ? "You" : document.getElementById("current-mentor-name").textContent;

    div.innerHTML = `
        <div class="message-label">${label}</div>
        <div class="message-content">${role === "user" ? escapeHtml(text) : text}</div>
    `;

    messages.appendChild(div);
    scrollToBottom();
    return div;
}

function addSystemMessage(text) {
    const messages = document.getElementById("messages");
    const div = document.createElement("div");
    div.className = "message system";
    div.innerHTML = `<div class="message-content system-content">${escapeHtml(text)}</div>`;
    messages.appendChild(div);
    scrollToBottom();
}

function scrollToBottom() {
    const el = document.getElementById("messages");
    el.scrollTop = el.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

async function clearChat() {
    try {
        await fetch("/api/clear", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mentor: state.mentor }),
        });
    } catch (e) { /* ok */ }

    const messages = document.getElementById("messages");
    messages.innerHTML = `
        <div class="welcome-message" id="welcome">
            <div class="welcome-icon">🎓</div>
            <h2>Welcome to Mentor AI</h2>
            <p>Pick a mentor from the sidebar and ask anything.<br>Upload code files for context-aware help.</p>
            <div class="quick-starts" id="quick-starts"></div>
        </div>
    `;
    renderQuickStarts(state.mentor);
}


// ── Sidebar toggle (mobile) ──

function toggleSidebar() {
    document.getElementById("sidebar").classList.toggle("open");
}
