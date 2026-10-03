"use client";

import { useEffect, useRef } from "react";

const VERT = `
attribute vec2 a_pos;
void main() {
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
`;

const FRAG = `
precision mediump float;
uniform vec2 u_res;
uniform float u_time;
uniform vec2 u_pointer;
uniform float u_light;
void main() {
  vec2 uv = gl_FragCoord.xy / u_res.xy;
  vec2 p = uv - vec2(0.5);
  p.x *= u_res.x / max(u_res.y, 1.0);
  vec2 aim = u_pointer - vec2(0.5);
  float wave = sin(p.x * 4.2 + u_time * 0.16) * cos(p.y * 3.1 - u_time * 0.11);
  float band = smoothstep(0.28, 0.0, abs(p.y - wave * 0.12));
  float pool = exp(-length(p - aim) * 2.1);
  float vignette = smoothstep(1.2, 0.2, length(p));
  vec3 darkInk = vec3(0.035, 0.047, 0.067);
  vec3 darkMist = vec3(0.10, 0.15, 0.17);
  vec3 lightInk = vec3(0.91, 0.93, 0.945);
  vec3 lightMist = vec3(0.76, 0.84, 0.82);
  vec3 ink = mix(darkInk, lightInk, u_light);
  vec3 mist = mix(darkMist, lightMist, u_light);
  vec3 signal = vec3(0.42, 0.62, 0.52);
  vec3 color = mix(ink, mist, band * 0.62 + pool * 0.22);
  color += signal * pool * 0.1;
  color *= mix(0.78, 1.0, vignette);
  gl_FragColor = vec4(color, 1.0);
}
`;

function compile(gl: WebGLRenderingContext, type: number, source: string) {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

export function Field() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { antialias: false, alpha: true, premultipliedAlpha: false });
    if (!gl) return;

    const vertex = compile(gl, gl.VERTEX_SHADER, VERT);
    const fragment = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vertex || !fragment) return;
    const program = gl.createProgram();
    if (!program) return;
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      canvas.style.display = "none";
      return;
    }
    gl.useProgram(program);

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, "a_pos");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

    const resolution = gl.getUniformLocation(program, "u_res");
    const time = gl.getUniformLocation(program, "u_time");
    const pointerUniform = gl.getUniformLocation(program, "u_pointer");
    const light = gl.getUniformLocation(program, "u_light");
    const pointer = { x: 0.72, y: 0.58 };
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    let alive = true;

    const draw = (now: number) => {
      if (!alive) return;
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const width = Math.max(1, Math.floor(rect.width * dpr));
      const height = Math.max(1, Math.floor(rect.height * dpr));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(resolution, canvas.width, canvas.height);
      gl.uniform1f(time, reduce ? 12 : now * 0.001);
      gl.uniform2f(pointerUniform, pointer.x, pointer.y);
      gl.uniform1f(light, document.documentElement.dataset.theme === "light" ? 1 : 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (!reduce) frame = window.requestAnimationFrame(draw);
    };

    const onPointer = (event: PointerEvent) => {
      pointer.x = event.clientX / Math.max(window.innerWidth, 1);
      pointer.y = 1 - event.clientY / Math.max(window.innerHeight, 1);
    };
    const onTheme = () => {
      if (reduce) draw(0);
    };
    window.addEventListener("pointermove", onPointer);
    const observer = new MutationObserver(onTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    frame = window.requestAnimationFrame(draw);

    return () => {
      alive = false;
      window.cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onPointer);
      observer.disconnect();
    };
  }, []);

  return (
    <div className="pointer-events-none fixed inset-0 z-0" aria-hidden="true">
      <canvas ref={canvasRef} className="h-full w-full" />
    </div>
  );
}
