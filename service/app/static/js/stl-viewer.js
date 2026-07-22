/* Dependency-free mesh viewer on raw WebGL.
   window.SQStlViewer.mount(canvas, arrayBuffer) -> { dispose() }
     Parses binary and ASCII STL, then renders it.
   window.SQStlViewer.mountMesh(canvas, float32Positions) -> { dispose() }
     Same viewer for a pre-tessellated triangle soup (9 floats per
     triangle); normals are computed per face. STEP previews use this.
   Centers and scales the mesh, renders with a directional-plus-ambient
   shader, orbits on drag, zooms on wheel or pinch. Renders only on
   demand so an idle model costs no CPU. */
(function () {
  "use strict";

  const CAP = 2000000; // triangles; past this the browser tab suffers

  function num(v) {
    const f = parseFloat(v);
    return isFinite(f) ? f : 0;
  }

  function capCheck(count) {
    if (count > CAP) {
      throw new Error(
        "This model has about " + (count / 1e6).toFixed(1) + " million triangles, " +
        "over the viewer's 2 million cap. Download it and open it in your slicer instead."
      );
    }
  }

  function faceNormal(ax, ay, az, bx, by, bz, cx, cy, cz) {
    const ux = bx - ax, uy = by - ay, uz = bz - az;
    const vx = cx - ax, vy = cy - ay, vz = cz - az;
    let nx = uy * vz - uz * vy;
    let ny = uz * vx - ux * vz;
    let nz = ux * vy - uy * vx;
    const len = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
    return [nx / len, ny / len, nz / len];
  }

  function decodeText(buf) {
    if (window.TextDecoder) return new TextDecoder().decode(buf);
    const bytes = new Uint8Array(buf);
    let out = "";
    const CHUNK = 65536;
    for (let i = 0; i < bytes.length; i += CHUNK) {
      out += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
    }
    return out;
  }

  function parseBinary(buf, count) {
    capCheck(count);
    const dv = new DataView(buf);
    const positions = new Float32Array(count * 9);
    const normals = new Float32Array(count * 9);
    let o = 84;
    for (let i = 0; i < count; i++) {
      const base = i * 9;
      let nx = dv.getFloat32(o, true);
      let ny = dv.getFloat32(o + 4, true);
      let nz = dv.getFloat32(o + 8, true);
      o += 12;
      for (let v = 0; v < 3; v++) {
        positions[base + v * 3] = dv.getFloat32(o, true);
        positions[base + v * 3 + 1] = dv.getFloat32(o + 4, true);
        positions[base + v * 3 + 2] = dv.getFloat32(o + 8, true);
        o += 12;
      }
      o += 2; // attribute byte count
      if (nx === 0 && ny === 0 && nz === 0) {
        const n = faceNormal(
          positions[base], positions[base + 1], positions[base + 2],
          positions[base + 3], positions[base + 4], positions[base + 5],
          positions[base + 6], positions[base + 7], positions[base + 8]
        );
        nx = n[0]; ny = n[1]; nz = n[2];
      }
      for (let v = 0; v < 3; v++) {
        normals[base + v * 3] = nx;
        normals[base + v * 3 + 1] = ny;
        normals[base + v * 3 + 2] = nz;
      }
    }
    return { positions: positions, normals: normals, count: count };
  }

  function parseAscii(text) {
    const positions = [];
    const normals = [];
    let currentNormal = null;
    let verts = [];
    let tris = 0;
    const lines = text.split("\n");
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (line.lastIndexOf("vertex", 0) === 0) {
        const p = line.split(/\s+/);
        verts.push(num(p[1]), num(p[2]), num(p[3]));
        if (verts.length === 9) {
          tris++;
          capCheck(tris);
          let n = currentNormal;
          if (!n || (n[0] === 0 && n[1] === 0 && n[2] === 0)) {
            n = faceNormal(
              verts[0], verts[1], verts[2],
              verts[3], verts[4], verts[5],
              verts[6], verts[7], verts[8]
            );
          }
          for (let v = 0; v < 9; v++) positions.push(verts[v]);
          for (let v = 0; v < 3; v++) normals.push(n[0], n[1], n[2]);
          verts = [];
        }
      } else if (line.lastIndexOf("facet", 0) === 0) {
        const p = line.split(/\s+/);
        currentNormal = [num(p[2]), num(p[3]), num(p[4])];
      } else if (line.lastIndexOf("endfacet", 0) === 0) {
        verts = [];
      }
    }
    if (!tris) throw new Error("No triangles found in this STL file.");
    return { positions: new Float32Array(positions), normals: new Float32Array(normals), count: tris };
  }

  function parse(buf) {
    if (!buf || buf.byteLength < 15) throw new Error("This file is too small to be an STL model.");
    const headLen = Math.min(buf.byteLength, 2048);
    const headBytes = new Uint8Array(buf, 0, headLen);
    let head = "";
    for (let i = 0; i < headLen; i++) head += String.fromCharCode(headBytes[i]);
    const looksAscii = /^\s*solid/i.test(head);
    // Exact binary layout wins even when the header starts with "solid".
    if (buf.byteLength >= 84) {
      const count = new DataView(buf).getUint32(80, true);
      if (buf.byteLength === 84 + count * 50) return parseBinary(buf, count);
    }
    if (looksAscii) {
      const text = decodeText(buf);
      if (text.indexOf("facet") !== -1) return parseAscii(text);
    }
    // Binary with trailing junk after the triangle table still parses.
    if (buf.byteLength >= 84) {
      const count = new DataView(buf).getUint32(80, true);
      if (count > 0 && 84 + count * 50 <= buf.byteLength) return parseBinary(buf, count);
    }
    throw new Error("This file does not look like an STL model.");
  }

  /* Center on the bounding box, scale to fit, and turn the usual Z-up STL
     orientation into the viewer's Y-up so models stand the right way. */
  function normalizeMesh(mesh) {
    const p = mesh.positions;
    const n = mesh.normals;
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    for (let i = 0; i < p.length; i += 3) {
      if (p[i] < minX) minX = p[i];
      if (p[i] > maxX) maxX = p[i];
      if (p[i + 1] < minY) minY = p[i + 1];
      if (p[i + 1] > maxY) maxY = p[i + 1];
      if (p[i + 2] < minZ) minZ = p[i + 2];
      if (p[i + 2] > maxZ) maxZ = p[i + 2];
    }
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const cz = (minZ + maxZ) / 2;
    const span = Math.max(maxX - minX, maxY - minY, maxZ - minZ) || 1;
    const s = 2 / span;
    for (let i = 0; i < p.length; i += 3) {
      const x = (p[i] - cx) * s;
      const y = (p[i + 1] - cy) * s;
      const z = (p[i + 2] - cz) * s;
      p[i] = x;
      p[i + 1] = z;
      p[i + 2] = -y;
      const nyv = n[i + 1];
      n[i + 1] = n[i + 2];
      n[i + 2] = -nyv;
    }
  }

  const VS =
    "attribute vec3 aPos;\n" +
    "attribute vec3 aNorm;\n" +
    "uniform mat4 uProj;\n" +
    "uniform mat4 uMV;\n" +
    "uniform mat3 uNorm;\n" +
    "varying vec3 vNormal;\n" +
    "void main() {\n" +
    "  vNormal = uNorm * aNorm;\n" +
    "  gl_Position = uProj * (uMV * vec4(aPos, 1.0));\n" +
    "}\n";

  const FS =
    "precision mediump float;\n" +
    "varying vec3 vNormal;\n" +
    "void main() {\n" +
    "  vec3 n = normalize(vNormal);\n" +
    "  vec3 l = normalize(vec3(0.35, 0.6, 1.0));\n" +
    "  float d = abs(dot(n, l));\n" +
    "  vec3 base = vec3(0.72, 0.67, 0.88);\n" +
    "  vec3 col = base * (0.28 + 0.72 * d);\n" +
    "  gl_FragColor = vec4(col, 1.0);\n" +
    "}\n";

  /* Triangle soup (9 floats per triangle) to the viewer's mesh shape,
     with flat per-face normals. */
  function buildSoupMesh(positions) {
    if (!(positions instanceof Float32Array)) positions = new Float32Array(positions);
    const count = Math.floor(positions.length / 9);
    if (!count) throw new Error("No triangles found in this model.");
    capCheck(count);
    if (positions.length !== count * 9) positions = positions.subarray(0, count * 9);
    const normals = new Float32Array(count * 9);
    for (let i = 0; i < count; i++) {
      const base = i * 9;
      const n = faceNormal(
        positions[base], positions[base + 1], positions[base + 2],
        positions[base + 3], positions[base + 4], positions[base + 5],
        positions[base + 6], positions[base + 7], positions[base + 8]
      );
      for (let v = 0; v < 3; v++) {
        normals[base + v * 3] = n[0];
        normals[base + v * 3 + 1] = n[1];
        normals[base + v * 3 + 2] = n[2];
      }
    }
    return { positions: positions, normals: normals, count: count };
  }

  function mount(canvas, arrayBuffer) {
    return mountParsed(canvas, parse(arrayBuffer));
  }

  function mountMesh(canvas, float32Positions) {
    return mountParsed(canvas, buildSoupMesh(float32Positions));
  }

  function mountParsed(canvas, mesh) {
    normalizeMesh(mesh);

    let gl = canvas.getContext("webgl", { antialias: true }) ||
      canvas.getContext("experimental-webgl", { antialias: true });
    if (!gl) {
      throw new Error("WebGL is not available in this browser, so the 3D preview cannot run. Download the file instead.");
    }

    let program = null, posBuf = null, normBuf = null;
    let aPos = 0, aNorm = 0, uProj = null, uMV = null, uNorm = null;
    let yaw = 0.7, pitch = 0.45, dist = 3;
    let dragging = false, lastX = 0, lastY = 0, pinch = 0;
    let rafPending = false, disposed = false, contextLost = false;

    function compile(type, src) {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        throw new Error("Shader error: " + gl.getShaderInfoLog(s));
      }
      return s;
    }

    function initResources() {
      program = gl.createProgram();
      gl.attachShader(program, compile(gl.VERTEX_SHADER, VS));
      gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FS));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        throw new Error("Shader link error: " + gl.getProgramInfoLog(program));
      }
      aPos = gl.getAttribLocation(program, "aPos");
      aNorm = gl.getAttribLocation(program, "aNorm");
      uProj = gl.getUniformLocation(program, "uProj");
      uMV = gl.getUniformLocation(program, "uMV");
      uNorm = gl.getUniformLocation(program, "uNorm");
      posBuf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
      gl.bufferData(gl.ARRAY_BUFFER, mesh.positions, gl.STATIC_DRAW);
      normBuf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, normBuf);
      gl.bufferData(gl.ARRAY_BUFFER, mesh.normals, gl.STATIC_DRAW);
      gl.enable(gl.DEPTH_TEST);
      gl.clearColor(0.016, 0.02, 0.04, 1); // matches --bg
    }

    function render() {
      if (!gl || disposed || contextLost) return;
      const w = canvas.width || 1;
      const h = canvas.height || 1;
      gl.viewport(0, 0, w, h);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.useProgram(program);
      gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
      gl.enableVertexAttribArray(aPos);
      gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, normBuf);
      gl.enableVertexAttribArray(aNorm);
      gl.vertexAttribPointer(aNorm, 3, gl.FLOAT, false, 0, 0);
      // Model-view: rotate yaw around Y, pitch around X, then pull back.
      const cy = Math.cos(yaw), sy = Math.sin(yaw);
      const cp = Math.cos(pitch), sp = Math.sin(pitch);
      const mv = [
        cy, sp * sy, -cp * sy, 0,
        0, cp, sp, 0,
        sy, -sp * cy, cp * cy, 0,
        0, 0, -dist, 1,
      ];
      const nm = [
        cy, sp * sy, -cp * sy,
        0, cp, sp,
        sy, -sp * cy, cp * cy,
      ];
      const f = 1 / Math.tan(Math.PI / 8); // 45 degree field of view
      const aspect = w / h, near = 0.1, far = 100;
      const proj = [
        f / aspect, 0, 0, 0,
        0, f, 0, 0,
        0, 0, (far + near) / (near - far), -1,
        0, 0, (2 * far * near) / (near - far), 0,
      ];
      gl.uniformMatrix4fv(uProj, false, proj);
      gl.uniformMatrix4fv(uMV, false, mv);
      gl.uniformMatrix3fv(uNorm, false, nm);
      gl.drawArrays(gl.TRIANGLES, 0, mesh.count * 3);
    }

    function invalidate() {
      if (rafPending || disposed) return;
      rafPending = true;
      requestAnimationFrame(() => {
        rafPending = false;
        if (!disposed) render();
      });
    }

    function resize() {
      if (disposed) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.max(1, Math.round((canvas.clientWidth || 1) * dpr));
      const h = Math.max(1, Math.round((canvas.clientHeight || 1) * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      invalidate();
    }

    function startDrag(x, y) {
      dragging = true;
      lastX = x;
      lastY = y;
    }

    function moveDrag(x, y) {
      if (!dragging) return;
      yaw += (x - lastX) * 0.011;
      pitch += (y - lastY) * 0.011;
      pitch = Math.max(-1.55, Math.min(1.55, pitch));
      lastX = x;
      lastY = y;
      invalidate();
    }

    function zoomBy(factor) {
      dist = Math.max(1.2, Math.min(15, dist * factor));
      invalidate();
    }

    function touchDist(e) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      return Math.sqrt(dx * dx + dy * dy);
    }

    const onMouseDown = (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      startDrag(e.clientX, e.clientY);
    };
    const onMouseMove = (e) => moveDrag(e.clientX, e.clientY);
    const onMouseUp = () => { dragging = false; };
    const onWheel = (e) => {
      e.preventDefault();
      zoomBy(Math.exp(e.deltaY * 0.0012));
    };
    const onTouchStart = (e) => {
      if (e.touches.length === 1) {
        startDrag(e.touches[0].clientX, e.touches[0].clientY);
      } else if (e.touches.length === 2) {
        dragging = false;
        pinch = touchDist(e);
      }
    };
    const onTouchMove = (e) => {
      e.preventDefault();
      if (e.touches.length === 1) {
        moveDrag(e.touches[0].clientX, e.touches[0].clientY);
      } else if (e.touches.length === 2) {
        const d = touchDist(e);
        if (pinch > 0 && d > 0) zoomBy(pinch / d);
        pinch = d;
      }
    };
    const onTouchEnd = () => {
      dragging = false;
      pinch = 0;
    };
    const onContextLost = (e) => {
      e.preventDefault();
      contextLost = true;
    };
    const onContextRestored = () => {
      contextLost = false;
      try {
        initResources();
        resize();
        invalidate();
      } catch (err) { /* the canvas stays dark; download still works */ }
    };

    canvas.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("touchstart", onTouchStart, { passive: true });
    canvas.addEventListener("touchmove", onTouchMove, { passive: false });
    canvas.addEventListener("touchend", onTouchEnd);
    canvas.addEventListener("touchcancel", onTouchEnd);
    canvas.addEventListener("webglcontextlost", onContextLost, false);
    canvas.addEventListener("webglcontextrestored", onContextRestored, false);

    let ro = null;
    if (window.ResizeObserver) {
      ro = new ResizeObserver(resize);
      ro.observe(canvas);
    } else {
      window.addEventListener("resize", resize);
    }

    function dispose() {
      if (disposed) return;
      disposed = true;
      if (ro) ro.disconnect();
      else window.removeEventListener("resize", resize);
      canvas.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("touchstart", onTouchStart);
      canvas.removeEventListener("touchmove", onTouchMove);
      canvas.removeEventListener("touchend", onTouchEnd);
      canvas.removeEventListener("touchcancel", onTouchEnd);
      canvas.removeEventListener("webglcontextlost", onContextLost);
      canvas.removeEventListener("webglcontextrestored", onContextRestored);
      try {
        if (gl && !contextLost) {
          gl.deleteBuffer(posBuf);
          gl.deleteBuffer(normBuf);
          gl.deleteProgram(program);
          const ext = gl.getExtension("WEBGL_lose_context");
          if (ext) ext.loseContext();
        }
      } catch (e) { /* ignore */ }
      gl = null;
    }

    initResources();
    resize();
    render();
    return { dispose: dispose };
  }

  window.SQStlViewer = { mount: mount, mountMesh: mountMesh };
})();
