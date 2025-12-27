(async function () {
  const districtCanvas = document.getElementById("districtChart");
  const clustersCanvas = document.getElementById("clustersChart");
  if (!districtCanvas || !clustersCanvas) return;
  function rgba(hex, a) {
    const h = hex.replace("#", "");
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${a})`;
  }
  function convexHull(points) {
    if (!points || points.length < 3) return points || [];
    const pts = points
      .map((p) => ({ x: Number(p.x), y: Number(p.y) }))
      .sort((a, b) => (a.x === b.x ? a.y - b.y : a.x - b.x));

    const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);

    const lower = [];
    for (const p of pts) {
      while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
        lower.pop();
      }
      lower.push(p);
    }

    const upper = [];
    for (let i = pts.length - 1; i >= 0; i--) {
      const p = pts[i];
      while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
        upper.pop();
      }
      upper.push(p);
    }

    upper.pop();
    lower.pop();
    return lower.concat(upper);
  }

  function centroid(poly) {
    if (!poly || poly.length === 0) return null;
    let sx = 0,
      sy = 0;
    for (const p of poly) {
      sx += p.x;
      sy += p.y;
    }
    return { x: sx / poly.length, y: sy / poly.length };
  }

  let payload;
  try {
    const res = await fetch("/api/stats", { cache: "no-store" });
    payload = await res.json();
  } catch (e) {
    console.error("Не удалось загрузить /api/stats", e);
    return;
  }

  const byDistrict = payload?.by_district || {};
  const clusters = payload?.clusters_scatter || { k: 0, points: [] };
  const districtLabels = Object.keys(byDistrict);
  const districtValues = districtLabels.map((k) => Number(byDistrict[k] || 0));

  new Chart(districtCanvas.getContext("2d"), {
    type: "bar",
    data: {
      labels: districtLabels,
      datasets: [
        {
          label: "Количество",
          data: districtValues,
          backgroundColor: rgba("#16a34a", 0.45),
          borderColor: rgba("#16a34a", 0.9),
          borderWidth: 2,
          borderRadius: 14,
          borderSkipped: false,
          maxBarThickness: 44,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 350 },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.parsed.y}`,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            maxRotation: 60,
            minRotation: 60,
            autoSkip: false,
            font: { size: 11 },
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(15, 23, 42, 0.08)" },
          ticks: { precision: 0 },
        },
      },
    },
  });

  const k = Number(clusters.k || 0);
  const points = Array.isArray(clusters.points) ? clusters.points : [];

  const clusterPalette = [
    { name: "Кластер 1", stroke: "#dc2626", fill: rgba("#dc2626", 0.10) }, 
    { name: "Кластер 2", stroke: "#2563eb", fill: rgba("#2563eb", 0.10) },
    { name: "Кластер 3", stroke: "#16a34a", fill: rgba("#16a34a", 0.10) },
  ];

  const byCluster = new Map();
  for (const p of points) {
    const c = Number(p.cluster ?? 0);
    if (!byCluster.has(c)) byCluster.set(c, []);
    byCluster.get(c).push({
      x: Number(p.lon),
      y: Number(p.lat),
      eco: Number(p.eco ?? 0),
    });
  }

  const scatterDatasets = [];
  const clusterIds = Array.from(byCluster.keys()).sort((a, b) => a - b);

  for (let idx = 0; idx < clusterIds.length; idx++) {
    const cid = clusterIds[idx];
    const style = clusterPalette[idx] || {
      name: `Кластер ${idx + 1}`,
      stroke: "#64748b",
      fill: rgba("#64748b", 0.10),
    };

    scatterDatasets.push({
      type: "scatter",
      label: style.name,
      data: byCluster.get(cid).map((p) => ({ x: p.x, y: p.y, eco: p.eco })),
      showLine: false,
      pointRadius: 4,
      pointHoverRadius: 6,
      pointBackgroundColor: rgba(style.stroke, 0.65),
      pointBorderColor: rgba(style.stroke, 0.95),
      pointBorderWidth: 1,
    });
  }
  const hullPlugin = {
    id: "clusterHulls",
    beforeDatasetsDraw(chart, args, pluginOptions) {
      const { ctx, chartArea } = chart;
      if (!chartArea) return;

      ctx.save();
      for (let di = 0; di < scatterDatasets.length; di++) {
        const ds = chart.data.datasets[di];
        if (!ds || !ds.data || ds.type !== "scatter") continue;

        const style = clusterPalette[di] || { stroke: "#64748b", fill: rgba("#64748b", 0.10) };

        const raw = ds.data
          .map((p) => ({ x: Number(p.x), y: Number(p.y) }))
          .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));

        if (raw.length < 3) continue;

        const hull = convexHull(raw);
        if (hull.length < 3) continue;

        const px = hull.map((p) => ({
          x: chart.scales.x.getPixelForValue(p.x),
          y: chart.scales.y.getPixelForValue(p.y),
        }));

        ctx.beginPath();
        ctx.moveTo(px[0].x, px[0].y);
        for (let i = 1; i < px.length; i++) ctx.lineTo(px[i].x, px[i].y);
        ctx.closePath();

        ctx.fillStyle = style.fill;
        ctx.fill();


        ctx.lineWidth = 2;
        ctx.strokeStyle = rgba(style.stroke, 0.95);
        ctx.stroke();
      }

      ctx.restore();
    },
  };

  new Chart(clustersCanvas.getContext("2d"), {
    type: "scatter",
    data: { datasets: scatterDatasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 350 },
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            boxWidth: 34,
            boxHeight: 10,
            usePointStyle: false,
          },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const eco = ctx.raw?.eco ? "эко" : "обычная";
              return ` ${ctx.dataset.label}: ${eco}, lat ${ctx.parsed.y.toFixed(4)}, lon ${ctx.parsed.x.toFixed(4)}`;
            },
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: "Долгота" },
          grid: { color: "rgba(15, 23, 42, 0.08)" },
        },
        y: {
          title: { display: true, text: "Широта" },
          grid: { color: "rgba(15, 23, 42, 0.08)" },
        },
      },
    },
    plugins: [hullPlugin],
  });
})();
