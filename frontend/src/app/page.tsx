export default function Home() {
  return (
    <main style={{ padding: "2rem", fontFamily: "monospace" }}>
      <h1>Trading System</h1>
      <p>K8s 기반 트레이딩 시스템 대시보드</p>
      <nav>
        <ul>
          <li><a href="/dashboard">대시보드</a></li>
          <li><a href="/journal">매매일지</a></li>
        </ul>
      </nav>
    </main>
  );
}
