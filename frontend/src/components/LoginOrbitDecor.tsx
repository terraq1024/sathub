// 登录/注册页品牌栏背景装饰：同心轨道环 + 渐变行星 + 卫星节点。
// 以绝对定位铺满品牌栏，右锚定裁切，不响应鼠标。
export function LoginOrbitDecor() {
  return (
    <svg
      className="login-orbit-decor"
      viewBox="0 0 860 960"
      preserveAspectRatio="xMaxYMid slice"
      aria-hidden
    >
      <defs>
        <radialGradient id="login-planet-grad" cx="50%" cy="40%" r="65%">
          <stop offset="0%" stopColor="#9DBCFA" stopOpacity="0.9" />
          <stop offset="55%" stopColor="#C2D5FC" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#DDE8FD" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="600" cy="430" r="215" fill="url(#login-planet-grad)" />
      <circle cx="600" cy="430" r="330" fill="none" stroke="#CCD8EC" strokeWidth="1.4" />
      <circle cx="600" cy="430" r="440" fill="none" stroke="#D5DFEE" strokeWidth="1.2" />
      <circle cx="600" cy="430" r="550" fill="none" stroke="#DEE6F2" strokeWidth="1.2" />
      <circle cx="367" cy="197" r="6" fill="#4A7DF6" />
      <circle cx="167" cy="506" r="5" fill="#8FB3F8" />
      <circle cx="760" cy="296" r="4" fill="#7C5CF5" />
    </svg>
  );
}
