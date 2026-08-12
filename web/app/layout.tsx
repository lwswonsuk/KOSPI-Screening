export const metadata = {
  title: "주식 스크리닝 — Stock Note Alpha",
  description: "코스피 종목 스크리닝 결과",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body
        style={{
          margin: 0,
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif",
          background: "#0b0d12",
          color: "#e6e6e6",
        }}
      >
        {children}
      </body>
    </html>
  );
}
