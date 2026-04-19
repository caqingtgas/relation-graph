(function kgGraphViewerApp() {
  var graphData = window.KG_GRAPH_DATA || { nodes: [], edges: [] };
  var graphOptions = window.KG_GRAPH_OPTIONS || {};
  var container = document.getElementById("graph-network");
  if (!container || typeof vis === "undefined") {
    return;
  }

  var nodes = new vis.DataSet((graphData.nodes || []).map(function(node) {
    return Object.assign({}, node);
  }));
  var edges = new vis.DataSet((graphData.edges || []).map(function(edge) {
    return Object.assign({}, edge, { label: "" });
  }));
  var network = new vis.Network(container, { nodes: nodes, edges: edges }, graphOptions);

  window.network = network;
  window.nodes = nodes;
  window.edges = edges;

  var allNodes = nodes.get({ returnType: "Object" });
  var allEdges = edges.get({ returnType: "Object" });
  var edgeLabelCache = {};
  var lastShowLabels = null;
  var highlightedNodeId = null;

  edges.forEach(function(edge) {
    edgeLabelCache[edge.id] = String(edge.label_text || edge.title || "")
      .replace(/<[^>]*>/g, "")
      .replace(/\s+/g, " ")
      .replace(/^主关系:\s*/, "")
      .trim();
  });

  function grayNodeColor() {
    return {
      background: "rgba(203, 213, 225, 0.55)",
      border: "rgba(148, 163, 184, 0.9)",
      highlight: {
        background: "rgba(203, 213, 225, 0.55)",
        border: "rgba(148, 163, 184, 0.9)"
      },
      hover: {
        background: "rgba(203, 213, 225, 0.55)",
        border: "rgba(148, 163, 184, 0.9)"
      }
    };
  }

  function cloneColorValue(colorValue, fallback) {
    if (colorValue && typeof colorValue === "object") {
      return Object.assign({}, colorValue);
    }
    if (typeof colorValue === "string" && colorValue) {
      return colorValue;
    }
    if (fallback && typeof fallback === "object") {
      return Object.assign({}, fallback);
    }
    return fallback || null;
  }

  function defaultEdgeColor(original) {
    return cloneColorValue(original.color, { inherit: "both" });
  }

  function resetHighlight() {
    var nodeUpdates = [];
    Object.keys(allNodes).forEach(function(id) {
      var original = allNodes[id];
      nodeUpdates.push({
        id: id,
        color: original.color,
        hiddenLabel: original.hiddenLabel || false,
        font: original.font
      });
    });

    var edgeUpdates = [];
    Object.keys(allEdges).forEach(function(id) {
      var original = allEdges[id];
      edgeUpdates.push({
        id: id,
        color: defaultEdgeColor(original),
        hidden: original.hidden || false
      });
    });

    if (nodeUpdates.length) {
      nodes.update(nodeUpdates);
    }
    if (edgeUpdates.length) {
      edges.update(edgeUpdates);
    }
    highlightedNodeId = null;
    lastShowLabels = null;
    updateEdgeLabels();
  }

  function neighbourhoodHighlight(params) {
    if (!params.nodes || params.nodes.length === 0) {
      resetHighlight();
      return;
    }

    highlightedNodeId = params.nodes[0];
    var connectedNodes = network.getConnectedNodes(highlightedNodeId);
    var connectedEdges = network.getConnectedEdges(highlightedNodeId);
    var activeNodeIds = new Set([highlightedNodeId].concat(connectedNodes));
    var activeEdgeIds = new Set(connectedEdges);

    var nodeUpdates = [];
    Object.keys(allNodes).forEach(function(id) {
      var original = allNodes[id];
      if (activeNodeIds.has(id)) {
        nodeUpdates.push({
          id: id,
          color: original.color,
          hiddenLabel: false,
          font: original.font
        });
      } else {
        nodeUpdates.push({
          id: id,
          color: grayNodeColor(),
          hiddenLabel: false,
          font: Object.assign({}, original.font || {}, { color: "rgba(100, 116, 139, 0.55)" })
        });
      }
    });

    var edgeUpdates = [];
    Object.keys(allEdges).forEach(function(id) {
      var original = allEdges[id];
      edgeUpdates.push({
        id: id,
        color: activeEdgeIds.has(id) ? defaultEdgeColor(original) : "rgba(203, 213, 225, 0.18)",
        hidden: false
      });
    });

    if (nodeUpdates.length) {
      nodes.update(nodeUpdates);
    }
    if (edgeUpdates.length) {
      edges.update(edgeUpdates);
    }
    updateEdgeLabels();
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function currentScale() {
    var scale = Number(network.getScale());
    return Number.isFinite(scale) && scale > 0 ? scale : null;
  }

  function formatScale(value) {
    return Number(value).toFixed(2);
  }

  var slider = document.getElementById("graph-zoom-slider");
  var valueNode = document.getElementById("graph-zoom-value");
  var thresholdSlider = document.getElementById("graph-threshold-slider");
  var fitButton = document.getElementById("graph-fit-btn");
  var ticksGroup = document.getElementById("graph-zoom-ticks");
  var thresholdMarker = document.getElementById("graph-threshold-marker");
  var zoomMarker = document.getElementById("graph-zoom-marker");
  var railConfigured = false;
  var captureTimer = null;
  var sliderSvgWidth = 284;
  var sliderBaseY = 20;
  var sliderTickCount = 41;

  function ensureTicks() {
    if (!ticksGroup || ticksGroup.childNodes.length > 0) {
      return;
    }
    for (var i = 0; i < sliderTickCount; i += 1) {
      var x = (i / (sliderTickCount - 1)) * sliderSvgWidth;
      var major = i % 8 === 0 || i === sliderTickCount - 1;
      var h = major ? 12 : 6;
      var line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", String(x));
      line.setAttribute("y1", String(sliderBaseY - h));
      line.setAttribute("x2", String(x));
      line.setAttribute("y2", String(sliderBaseY));
      line.setAttribute("stroke", "rgba(15,23,42,0.42)");
      line.setAttribute("stroke-width", "1");
      ticksGroup.appendChild(line);
    }
  }

  function sliderMin() {
    return Number(slider.min || "0.05");
  }

  function sliderMax() {
    return Number(slider.max || "5");
  }

  function thresholdMin() {
    return Number(thresholdSlider.min || slider.min || "0.05");
  }

  function thresholdMax() {
    return Number(thresholdSlider.max || slider.max || "5");
  }

  function thresholdScale() {
    return clamp(Number(thresholdSlider.value || slider.value || "1"), thresholdMin(), thresholdMax());
  }

  function syncThresholdTag() {
    if (!thresholdMarker) {
      return thresholdScale();
    }
    var min = thresholdMin();
    var max = thresholdMax();
    var scale = thresholdScale();
    var ratio = max === min ? 0 : (scale - min) / (max - min);
    var x = ratio * sliderSvgWidth;
    thresholdMarker.setAttribute(
      "points",
      x + "," + sliderBaseY + " " + (x - 6) + "," + (sliderBaseY - 11) + " " + (x + 6) + "," + (sliderBaseY - 11)
    );
    return scale;
  }

  function syncZoomMarker(scale) {
    if (!zoomMarker && !valueNode) {
      return;
    }
    var min = sliderMin();
    var max = sliderMax();
    var clampedScale = clamp(scale, min, max);
    var ratio = max === min ? 0 : (clampedScale - min) / (max - min);
    var x = ratio * sliderSvgWidth;
    if (zoomMarker) {
      zoomMarker.setAttribute("cx", String(x));
    }
    if (valueNode) {
      valueNode.style.left = x + "px";
    }
  }

  function configureRail(referenceScale) {
    if (!Number.isFinite(referenceScale) || referenceScale <= 0) {
      return;
    }
    if (!railConfigured) {
      var min = Math.max(0.05, referenceScale * 0.25);
      var max = Math.max(referenceScale * 4, min + 0.5);
      slider.min = min.toFixed(2);
      slider.max = max.toFixed(2);
      thresholdSlider.min = slider.min;
      thresholdSlider.max = slider.max;
      thresholdSlider.value = String(clamp(referenceScale * 1.5, min, max));
      railConfigured = true;
    }
    var clampedScale = clamp(referenceScale, sliderMin(), sliderMax());
    slider.value = String(clampedScale);
    valueNode.textContent = formatScale(clampedScale);
    syncZoomMarker(clampedScale);
    syncThresholdTag();
  }

  function updateEdgeLabels() {
    var scale = currentScale();
    if (scale === null) {
      return;
    }

    var showLabels = scale >= thresholdScale();
    if (lastShowLabels === showLabels && highlightedNodeId === null) {
      return;
    }
    lastShowLabels = showLabels;

    var connectedEdgeIds = highlightedNodeId ? new Set(network.getConnectedEdges(highlightedNodeId)) : null;
    var updates = [];
    edges.forEach(function(edge) {
      var label = showLabels ? (edgeLabelCache[edge.id] || "") : "";
      var isActive = connectedEdgeIds ? connectedEdgeIds.has(edge.id) : true;
      updates.push({
        id: edge.id,
        label: label,
        font: showLabels
          ? {
              align: "middle",
              size: isActive ? 10 : 9,
              strokeWidth: isActive ? 2 : 1,
              strokeColor: "#ffffff",
              color: isActive ? "#334155" : "rgba(100, 116, 139, 0.65)"
            }
          : {
              align: "middle",
              size: 0,
              strokeWidth: 0,
              strokeColor: "transparent",
              color: "transparent"
            }
      });
    });
    if (updates.length > 0) {
      edges.update(updates);
    }
  }

  function scheduleInitialCapture(delayMs) {
    if (railConfigured) {
      return;
    }
    if (captureTimer) {
      window.clearTimeout(captureTimer);
    }
    captureTimer = window.setTimeout(function() {
      var scale = currentScale();
      if (scale !== null) {
        configureRail(scale);
        updateEdgeLabels();
      }
    }, delayMs);
  }

  slider.addEventListener("input", function() {
    var targetScale = clamp(Number(slider.value), sliderMin(), sliderMax());
    valueNode.textContent = formatScale(targetScale);
    syncZoomMarker(targetScale);
    network.moveTo({
      position: network.getViewPosition(),
      scale: targetScale,
      animation: false
    });
    updateEdgeLabels();
  });

  thresholdSlider.addEventListener("input", function() {
    thresholdSlider.value = String(clamp(Number(thresholdSlider.value), thresholdMin(), thresholdMax()));
    syncThresholdTag();
    updateEdgeLabels();
  });

  fitButton.addEventListener("click", function() {
    network.fit({ animation: { duration: 300, easingFunction: "easeInOutQuad" } });
    highlightedNodeId = null;
    lastShowLabels = null;
    updateEdgeLabels();
  });

  network.on("click", function(params) {
    if (!params.nodes || params.nodes.length === 0) {
      resetHighlight();
      return;
    }
    neighbourhoodHighlight(params);
  });
  network.on("stabilized", function() {
    scheduleInitialCapture(220);
  });
  network.on("animationFinished", function() {
    if (!railConfigured) {
      scheduleInitialCapture(80);
      return;
    }
    var scale = currentScale();
    if (scale !== null) {
      slider.value = String(clamp(scale, sliderMin(), sliderMax()));
      valueNode.textContent = formatScale(scale);
      syncZoomMarker(scale);
    }
    updateEdgeLabels();
  });
  network.on("zoom", function() {
    var scale = currentScale();
    if (scale !== null) {
      if (!railConfigured) {
        configureRail(scale);
      } else {
        slider.value = String(clamp(scale, sliderMin(), sliderMax()));
        valueNode.textContent = formatScale(scale);
        syncZoomMarker(scale);
      }
    }
    updateEdgeLabels();
  });
  network.on("resize", function() {
    if (!railConfigured) {
      scheduleInitialCapture(180);
    }
  });
  network.on("afterDrawing", function() {
    if (!railConfigured) {
      scheduleInitialCapture(180);
    }
  });

  var immediateScale = currentScale();
  ensureTicks();
  if (immediateScale !== null) {
    configureRail(immediateScale);
  }
  syncThresholdTag();
  updateEdgeLabels();
})();
