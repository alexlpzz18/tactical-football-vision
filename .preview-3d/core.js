/* ═══════════════════════════════════════════════════════════════════════
   NÚCLEO — matrices, compilación de shaders y utilidades de WebGL2.
   Escrito a mano a propósito: sin dependencias no hay nada que descargar
   ni que se rompa al actualizar.
   ═══════════════════════════════════════════════════════════════════════ */

/* ---------- mat4 (column-major, como espera WebGL) ---------- */
const M4 = {
  ident(){ return new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]); },

  perspectiva(fovY, aspect, near, far){
    const f = 1/Math.tan(fovY/2), nf = 1/(near-far);
    return new Float32Array([
      f/aspect,0,0,0,  0,f,0,0,
      0,0,(far+near)*nf,-1,  0,0,2*far*near*nf,0]);
  },

  mirar(ojo, centro, arriba){
    let zx=ojo[0]-centro[0], zy=ojo[1]-centro[1], zz=ojo[2]-centro[2];
    let l=Math.hypot(zx,zy,zz)||1; zx/=l; zy/=l; zz/=l;
    let xx=arriba[1]*zz-arriba[2]*zy, xy=arriba[2]*zx-arriba[0]*zz, xz=arriba[0]*zy-arriba[1]*zx;
    l=Math.hypot(xx,xy,xz)||1; xx/=l; xy/=l; xz/=l;
    const yx=zy*xz-zz*xy, yy=zz*xx-zx*xz, yz=zx*xy-zy*xx;
    return new Float32Array([
      xx,yx,zx,0, xy,yy,zy,0, xz,yz,zz,0,
      -(xx*ojo[0]+xy*ojo[1]+xz*ojo[2]),
      -(yx*ojo[0]+yy*ojo[1]+yz*ojo[2]),
      -(zx*ojo[0]+zy*ojo[1]+zz*ojo[2]), 1]);
  },

  mul(a,b){
    const o=new Float32Array(16);
    for(let c=0;c<4;c++) for(let r=0;r<4;r++){
      o[c*4+r]=a[r]*b[c*4]+a[4+r]*b[c*4+1]+a[8+r]*b[c*4+2]+a[12+r]*b[c*4+3];
    }
    return o;
  },

  invertir(m){
    const o=new Float32Array(16);
    const a00=m[0],a01=m[1],a02=m[2],a03=m[3], a10=m[4],a11=m[5],a12=m[6],a13=m[7],
          a20=m[8],a21=m[9],a22=m[10],a23=m[11], a30=m[12],a31=m[13],a32=m[14],a33=m[15];
    const b00=a00*a11-a01*a10, b01=a00*a12-a02*a10, b02=a00*a13-a03*a10,
          b03=a01*a12-a02*a11, b04=a01*a13-a03*a11, b05=a02*a13-a03*a12,
          b06=a20*a31-a21*a30, b07=a20*a32-a22*a30, b08=a20*a33-a23*a30,
          b09=a21*a32-a22*a31, b10=a21*a33-a23*a31, b11=a22*a33-a23*a32;
    let det=b00*b11-b01*b10+b02*b09+b03*b08-b04*b07+b05*b06;
    if(!det) return M4.ident();
    det=1/det;
    o[0]=(a11*b11-a12*b10+a13*b09)*det;  o[1]=(a02*b10-a01*b11-a03*b09)*det;
    o[2]=(a31*b05-a32*b04+a33*b03)*det;  o[3]=(a22*b04-a21*b05-a23*b03)*det;
    o[4]=(a12*b08-a10*b11-a13*b07)*det;  o[5]=(a00*b11-a02*b08+a03*b07)*det;
    o[6]=(a32*b02-a30*b05-a33*b01)*det;  o[7]=(a20*b05-a22*b02+a23*b01)*det;
    o[8]=(a10*b10-a11*b08+a13*b06)*det;  o[9]=(a01*b08-a00*b10-a03*b06)*det;
    o[10]=(a30*b04-a31*b02+a33*b00)*det; o[11]=(a21*b02-a20*b04-a23*b00)*det;
    o[12]=(a11*b07-a10*b09-a12*b06)*det; o[13]=(a00*b09-a01*b07+a02*b06)*det;
    o[14]=(a31*b01-a30*b03-a32*b00)*det; o[15]=(a20*b03-a21*b01+a22*b00)*det;
    return o;
  },
};

/* ---------- utilidades ---------- */
const lim  = (v,a,b)=> v<a?a:(v>b?b:v);
const mez  = (a,b,t)=> a+(b-a)*t;
const suave= t=> t*t*(3-2*t);
const suave5=t=> t*t*t*(t*(t*6-15)+10);
/* facilita entradas y salidas sin que se note el arranque */
const easeIO= t=> t<0.5 ? 4*t*t*t : 1-Math.pow(-2*t+2,3)/2;

function compilar(gl, tipo, fuente, nombre){
  const s = gl.createShader(tipo);
  gl.shaderSource(s, fuente);
  gl.compileShader(s);
  if(!gl.getShaderParameter(s, gl.COMPILE_STATUS)){
    const log = gl.getShaderInfoLog(s);
    console.error(`[shader ${nombre}]`, log);
    throw new Error(`Shader ${nombre}: ${log}`);
  }
  return s;
}

function programa(gl, vs, fs, nombre){
  const p = gl.createProgram();
  gl.attachShader(p, compilar(gl, gl.VERTEX_SHADER, vs, nombre+':vs'));
  gl.attachShader(p, compilar(gl, gl.FRAGMENT_SHADER, fs, nombre+':fs'));
  gl.linkProgram(p);
  if(!gl.getProgramParameter(p, gl.LINK_STATUS)){
    const log = gl.getProgramInfoLog(p);
    console.error(`[program ${nombre}]`, log);
    throw new Error(`Program ${nombre}: ${log}`);
  }
  /* cachea las localizaciones para no pedirlas cada frame */
  p.u = new Proxy({}, {
    get(cache, k){
      if(!(k in cache)) cache[k] = gl.getUniformLocation(p, k);
      return cache[k];
    }
  });
  return p;
}

function bufferQuad(gl){
  const b = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, b);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
  return b;
}
