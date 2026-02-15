// GPU History for graph
const gpuHistory = {
    memory: [],
    compute: [],
    maxPoints: 20  // 20 points at 3s intervals = 60 seconds
};

async function loadGPU() {
    try {
        const data = await fetchAPI('/gpu');
        renderGPU(data.gpus);
        updateGPUHistory(data.gpus);
        drawGPUGraph();
    } catch (error) {
        console.error('Failed to load GPU stats:', error);
        document.getElementById('gpu-stats').innerHTML = `
            <div class="bg-red-900 p-4 rounded border border-red-700">
                <p class="text-red-200">Failed to load GPU stats: ${error.message}</p>
            </div>
        `;
    }
}

function updateGPUHistory(gpus) {
    if (!gpus || gpus.length === 0) return;

    // Use first GPU's stats
    const gpu = gpus[0];
    const memoryPercent = Math.round((gpu.memory.used / gpu.memory.total) * 100);
    const computePercent = gpu.utilization.gpu_percent;

    // Add to history
    gpuHistory.memory.push(memoryPercent);
    gpuHistory.compute.push(computePercent);

    // Trim to max points
    if (gpuHistory.memory.length > gpuHistory.maxPoints) {
        gpuHistory.memory.shift();
        gpuHistory.compute.shift();
    }

    // Show graph container once we have data
    document.getElementById('gpu-graph-container').classList.remove('hidden');
}

function drawGPUGraph() {
    const canvas = document.getElementById('gpu-graph');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const rect = canvas.getBoundingClientRect();

    // Set canvas size for high DPI
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = 80 * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = 80;
    const padding = 2;

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Draw grid lines
    ctx.strokeStyle = '#374151';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
        const y = padding + (height - 2 * padding) * (i / 4);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
    }

    if (gpuHistory.memory.length < 2) return;

    const pointWidth = (width - 2 * padding) / (gpuHistory.maxPoints - 1);
    const dataLen = gpuHistory.memory.length;

    // Draw memory line (blue) - right to left flow
    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth = 2;
    ctx.beginPath();
    gpuHistory.memory.forEach((value, i) => {
        // Position from right: newest value at right edge
        const x = width - padding - (dataLen - 1 - i) * pointWidth;
        const y = height - padding - (value / 100) * (height - 2 * padding);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Draw compute line (green) - right to left flow
    ctx.strokeStyle = '#22c55e';
    ctx.lineWidth = 2;
    ctx.beginPath();
    gpuHistory.compute.forEach((value, i) => {
        // Position from right: newest value at right edge
        const x = width - padding - (dataLen - 1 - i) * pointWidth;
        const y = height - padding - (value / 100) * (height - 2 * padding);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Draw current values
    const lastMem = gpuHistory.memory[gpuHistory.memory.length - 1];
    const lastComp = gpuHistory.compute[gpuHistory.compute.length - 1];

    ctx.font = '10px monospace';
    ctx.fillStyle = '#3b82f6';
    ctx.fillText(`${lastMem}%`, width - 30, 12);
    ctx.fillStyle = '#22c55e';
    ctx.fillText(`${lastComp}%`, width - 30, 24);
}

function renderGPU(gpus) {
    const container = document.getElementById('gpu-stats');

    if (!gpus || gpus.length === 0) {
        container.innerHTML = '<div class="text-gray-400">No GPU information available</div>';
        return;
    }

    container.innerHTML = gpus.map((gpu, idx) => {
        const memoryPercent = Math.round((gpu.memory.used / gpu.memory.total) * 100);
        const memoryBar = `
            <div class="w-full bg-gray-700 rounded h-2 mt-1">
                <div class="bg-blue-600 h-2 rounded" style="width: ${memoryPercent}%"></div>
            </div>
        `;

        return `
            <div class="bg-gray-800 p-4 rounded border border-gray-700">
                <p class="font-bold text-lg mb-2">${gpu.name}</p>
                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <p class="text-gray-400">Memory</p>
                        <p class="text-white font-mono">${gpu.memory.used}/${gpu.memory.total} MiB</p>
                        ${memoryBar}
                    </div>
                    <div>
                        <p class="text-gray-400">Temperature</p>
                        <p class="text-white font-mono">${gpu.temperature.current}°C</p>
                    </div>
                    <div>
                        <p class="text-gray-400">GPU Utilization</p>
                        <p class="text-white font-mono">${gpu.utilization.gpu_percent}%</p>
                    </div>
                    <div>
                        <p class="text-gray-400">Power</p>
                        <p class="text-white font-mono">${gpu.power.draw.toFixed(1)}/${gpu.power.limit.current.toFixed(0)} W</p>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}
