(() => {
  const canvas = document.getElementById("landingMonteCarlo");
  if (!canvas) return;
  const context = canvas.getContext("2d", { alpha: true });
  if (!context) return;

  const motionQuery = matchMedia("(prefers-reduced-motion: reduce)");
  const pathCount = 64;
  const stepCount = 96;
  const cycleDuration = 7200;
  const strike = 108;
  const premium = 4;
  const breakeven = 100 - premium;
  let width = 0, height = 0, frame = 0;
  let cycleStarted = performance.now(), visible = true, current = null, seed = 0x4e49434f;

  const randomGenerator = (initialSeed) => {
    let value = initialSeed >>> 0;
    return () => {
      value += 0x6d2b79f5;
      let result = value;
      result = Math.imul(result ^ result >>> 15, result | 1);
      result ^= result + Math.imul(result ^ result >>> 7, result | 61);
      return ((result ^ result >>> 14) >>> 0) / 4294967296;
    };
  };
  const normalSample = (random) => {
    const first = Math.max(Number.EPSILON, random());
    return Math.sqrt(-2 * Math.log(first)) * Math.cos(Math.PI * 2 * random());
  };
  const quantile = (values, ratio) => {
    const ordered = [...values].sort((a, b) => a - b);
    return ordered[Math.min(ordered.length - 1, Math.max(0, Math.round((ordered.length - 1) * ratio)))];
  };

  const createSimulation = () => {
    seed = (seed + 0x9e3779b9) >>> 0;
    const random = randomGenerator(seed), drift = 0.045, volatility = 0.24, timeStep = 1 / (stepCount - 1);
    const paths = Array.from({ length: pathCount }, () => {
      const values = [100];
      for (let index = 1; index < stepCount; index += 1) {
        const shock = normalSample(random);
        values.push(values[index - 1] * Math.exp((drift - volatility ** 2 / 2) * timeStep + volatility * Math.sqrt(timeStep) * shock));
      }
      return values;
    });
    const median = Array.from({ length: stepCount }, (_, index) => quantile(paths.map((path) => path[index]), .5));
    const values = [...paths.flat(), strike, breakeven], low = quantile(values, .012), high = quantile(values, .988), padding = Math.max(2, (high - low) * .1);
    const payoffs = paths.map((path) => Math.min(path.at(-1), strike) - 100 + premium), payoffMin = Math.min(...payoffs), payoffMax = Math.max(...payoffs), bins = Array.from({ length: 12 }, () => 0);
    payoffs.forEach((value) => { const ratio = (value - payoffMin) / Math.max(1, payoffMax - payoffMin); bins[Math.min(bins.length - 1, Math.floor(ratio * bins.length))] += 1; });
    return { paths, median, bins, minimum: low - padding, maximum: high + padding };
  };

  const palette = () => {
    const styles = getComputedStyle(document.documentElement);
    return {
      ink: styles.getPropertyValue("--editorial-ink").trim() || "#111113",
      muted: styles.getPropertyValue("--editorial-muted").trim() || "#6b6b72",
      faint: styles.getPropertyValue("--editorial-faint").trim() || "#9a9aa1",
      line: styles.getPropertyValue("--editorial-line").trim() || "#dcdce0",
      wash: styles.getPropertyValue("--editorial-wash").trim() || "#f0f0f2",
    };
  };
  const layout = () => ({ left: 10, top: 22, bottom: height - 22, expiry: width * .73, right: width - 8 });
  const priceY = (simulation, value) => { const box = layout(); return box.top + (simulation.maximum - value) / Math.max(1, simulation.maximum - simulation.minimum) * (box.bottom - box.top); };
  const point = (simulation, value, index) => { const box = layout(); return [box.left + index / (stepCount - 1) * (box.expiry - box.left), priceY(simulation, value)]; };

  const resize = () => {
    const bounds = canvas.getBoundingClientRect(), ratio = Math.min(2, window.devicePixelRatio || 1);
    width = Math.max(1, bounds.width); height = Math.max(1, bounds.height);
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0); drawStaticFrame();
  };

  const drawStructure = (simulation, colors) => {
    const box = layout();
    context.clearRect(0, 0, width, height);
    context.fillStyle = colors.wash; context.globalAlpha = .48;
    context.fillRect(box.left, box.top, box.expiry - box.left, Math.max(0, priceY(simulation, strike) - box.top));
    context.globalAlpha = 1; context.strokeStyle = colors.line; context.lineWidth = 1;
    for (let index = 1; index < 4; index += 1) { const x = box.left + index / 4 * (box.expiry - box.left); context.beginPath(); context.moveTo(x + .5, box.top); context.lineTo(x + .5, box.bottom); context.stroke(); }
    [strike, breakeven].forEach((value, index) => {
      const y = priceY(simulation, value);
      context.setLineDash(index ? [3, 5] : [7, 5]); context.strokeStyle = index ? colors.faint : colors.muted;
      context.beginPath(); context.moveTo(box.left, y); context.lineTo(box.expiry, y); context.stroke(); context.setLineDash([]);
      context.fillStyle = colors.muted; context.font = "10px ui-monospace, monospace"; context.textAlign = "left";
      context.fillText(index ? "BREAKEVEN 96" : "STRIKE 108", box.left + 5, index ? y + 12 : y - 6);
    });
    context.strokeStyle = colors.ink; context.globalAlpha = .62; context.beginPath(); context.moveTo(box.expiry + .5, box.top); context.lineTo(box.expiry + .5, box.bottom); context.stroke(); context.globalAlpha = 1;
    context.fillStyle = colors.muted; context.font = "10px ui-monospace, monospace"; context.textAlign = "center";
    context.fillText("EXPIRY", box.expiry, 12); context.fillText("TERMINAL P&L", (box.expiry + box.right) / 2, 12);
  };

  const trace = (simulation, values, progress, color, alpha, lineWidth) => {
    const lastPosition = Math.max(1, progress * (stepCount - 1)), lastIndex = Math.min(stepCount - 1, Math.floor(lastPosition));
    context.beginPath();
    for (let index = 0; index <= lastIndex; index += 1) { const [x, y] = point(simulation, values[index], index); if (!index) context.moveTo(x, y); else context.lineTo(x, y); }
    context.globalAlpha = alpha; context.strokeStyle = color; context.lineWidth = lineWidth; context.stroke(); context.globalAlpha = 1;
  };

  const drawDistribution = (simulation, reveal, colors) => {
    const box = layout(), panelWidth = box.right - box.expiry - 18, gap = 3, barWidth = (panelWidth - gap * (simulation.bins.length - 1)) / simulation.bins.length, maximum = Math.max(...simulation.bins, 1), baseline = box.bottom;
    context.globalAlpha = Math.max(0, Math.min(1, reveal));
    simulation.bins.forEach((count, index) => { const barHeight = count / maximum * (box.bottom - box.top - 22), x = box.expiry + 12 + index * (barWidth + gap); context.fillStyle = index < 4 ? colors.faint : colors.ink; context.fillRect(x, baseline - barHeight, Math.max(1, barWidth), barHeight); });
    context.strokeStyle = colors.line; context.beginPath(); context.moveTo(box.expiry + 10, baseline + .5); context.lineTo(box.right, baseline + .5); context.stroke(); context.globalAlpha = 1;
  };

  const drawSimulation = (simulation, progress, colors) => {
    simulation.paths.forEach((path, index) => trace(simulation, path, progress, colors.ink, index % 11 === 0 ? .22 : .075, index % 11 === 0 ? 1 : .65));
    trace(simulation, simulation.median, progress, colors.ink, .95, 1.8);
    const box = layout(), sweepX = box.left + progress * (box.expiry - box.left);
    context.strokeStyle = colors.ink; context.globalAlpha = .22 * (1 - Math.max(0, progress - .92) / .08); context.beginPath(); context.moveTo(sweepX, box.top); context.lineTo(sweepX, box.bottom); context.stroke(); context.globalAlpha = 1;
    drawDistribution(simulation, (progress - .72) / .28, colors);
  };
  const drawStaticFrame = () => { if (!current || !width || !height) return; const colors = palette(); drawStructure(current, colors); drawSimulation(current, 1, colors); };
  const animate = (now) => {
    if (!visible || document.hidden || motionQuery.matches) { frame = 0; drawStaticFrame(); return; }
    let elapsed = now - cycleStarted;
    if (elapsed >= cycleDuration) { current = createSimulation(); cycleStarted = now; elapsed = 0; }
    const progress = 1 - Math.pow(1 - Math.min(1, elapsed / cycleDuration / .84), 3), colors = palette();
    drawStructure(current, colors); drawSimulation(current, progress, colors); frame = requestAnimationFrame(animate);
  };
  const start = () => { cancelAnimationFrame(frame); frame = 0; if (motionQuery.matches || !visible || document.hidden) { drawStaticFrame(); return; } cycleStarted = performance.now(); frame = requestAnimationFrame(animate); };

  current = createSimulation();
  new ResizeObserver(resize).observe(canvas);
  new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; start(); }, { threshold: .05 }).observe(canvas);
  document.addEventListener("visibilitychange", start); motionQuery.addEventListener("change", start); resize(); start();
})();
