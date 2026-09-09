// 기본 화면은 비전문가용이다. 지금까지의 전문가 화면은 없애지 않고
// '자세히 보기'(plain/ExpertView) 안에 접어 넣었다 — 두 사용자층에 두 시각 언어가 대응한다.
import React from 'react';
import PlainApp from './plain/PlainApp';

export default function App() {
  return <PlainApp />;
}
