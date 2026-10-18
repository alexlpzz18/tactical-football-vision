function normalizar(p) {
  const n = p.length; let mx = 0, my = 0;
  for (const [x, y] of p) { mx += x / n; my += y / n; }
  let d = 0; for (const [x, y] of p) d += Math.hypot(x - mx, y - my) / n;
  const s = Math.SQRT2 / (d || 1);
  return [[s, 0, -s * mx], [0, s, -s * my], [0, 0, 1]];
}
function aplicar(T, x, y) {
  const w = T[2][0] * x + T[2][1] * y + T[2][2];
  return [(T[0][0] * x + T[0][1] * y + T[0][2]) / w, (T[1][0] * x + T[1][1] * y + T[1][2]) / w];
}
function mult(A, B) {
  return A.map((f, i) => B[0].map((_, j) => f.reduce((s, _v, k) => s + A[i][k] * B[k][j], 0)));
}
function inversa3(m) {
  const [a, b, c] = m[0], [d, e, f] = m[1], [g, h, i] = m[2];
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C;
  return [[A / det, -(b * i - c * h) / det, (b * f - c * e) / det],
          [B / det, (a * i - c * g) / det, -(a * f - c * d) / det],
          [C / det, -(a * h - b * g) / det, (a * e - b * d) / det]];
}
function resolver(A, b) {  // eliminación gaussiana con pivote parcial
  const n = b.length; const M = A.map((f, i) => [...f, b[i]]);
  for (let c = 0; c < n; c++) {
    let p = c; for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    if (Math.abs(M[c][c]) < 1e-12) return null;
    for (let r = 0; r < n; r++) if (r !== c) {
      const f = M[r][c] / M[c][c]; for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
    }
  }
  return M.map((f, i) => f[n] / f[i]);
}
// H que lleva los puntos `origen` a `destino` (≥ 4 pares), con h33 = 1.
function homografia(origen, destino) {
  const T1 = normalizar(origen), T2 = normalizar(destino);
  const o = origen.map(([x, y]) => aplicar(T1, x, y)), d = destino.map(([x, y]) => aplicar(T2, x, y));
  const AtA = Array.from({length: 8}, () => Array(8).fill(0)), Atb = Array(8).fill(0);
  for (let i = 0; i < o.length; i++) {
    const [x, y] = o[i], [u, v] = d[i];
    const filas = [[x, y, 1, 0, 0, 0, -u * x, -u * y, u], [0, 0, 0, x, y, 1, -v * x, -v * y, v]];
    for (const f of filas) for (let r = 0; r < 8; r++) {
      Atb[r] += f[r] * f[8]; for (let c = 0; c < 8; c++) AtA[r][c] += f[r] * f[c];
    }
  }
  const h = resolver(AtA, Atb); if (!h) return null;
  const Hn = [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1]];
  const H = mult(inversa3(T2), mult(Hn, T1)); const k = H[2][2];
  return refinar(H.map(f => f.map(v => v / k)), origen, destino);
}
// Refinado del error de REPROYECCIÓN (Levenberg-Marquardt con jacobiano numérico), como
// hace OpenCV tras el DLT. Sin él, con más de 4 puntos, el DLT algebraico se separaba
// hasta 0,5 m de calcular_homografia en los puntos lejanos (medido con los 19 clics).
function refinar(H, origen, destino) {
  if (origen.length <= 4) return H;
  const vec = M => [M[0][0], M[0][1], M[0][2], M[1][0], M[1][1], M[1][2], M[2][0], M[2][1]];
  const mat = h => [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1]];
  const res = h => { const M = mat(h); const r = [];
    for (let i = 0; i < origen.length; i++) { const p = aplicar(M, ...origen[i]); r.push(p[0] - destino[i][0], p[1] - destino[i][1]); }
    return r; };
  const coste = r => r.reduce((s, v) => s + v * v, 0);
  let h = vec(H), r = res(h), c = coste(r), lam = 1e-3;
  for (let it = 0; it < 50; it++) {
    const J = h.map((v, j) => { const e = Math.max(Math.abs(v) * 1e-6, 1e-10); const hh = [...h]; hh[j] += e;
      return res(hh).map((x, i) => (x - r[i]) / e); });  // J[j][i] = d r_i / d h_j
    const JtJ = J.map(a => J.map(b => a.reduce((s, x, i) => s + x * b[i], 0)));
    const Jtr = J.map(a => a.reduce((s, x, i) => s + x * r[i], 0));
    let mejora = false;
    for (let t = 0; t < 10; t++) {
      const A = JtJ.map((f, i) => f.map((v, j) => v + (i === j ? lam * (JtJ[i][i] || 1) : 0)));
      const d = resolver(A, Jtr.map(v => -v)); if (!d) break;
      const hn = h.map((v, j) => v + d[j]), rn = res(hn), cn = coste(rn);
      if (cn < c) { h = hn; r = rn; mejora = Math.abs(c - cn) > 1e-12 * c; c = cn; lam = Math.max(lam / 10, 1e-12); break; }
      lam *= 10;
    }
    if (!mejora) break;
  }
  return mat(h);
}
