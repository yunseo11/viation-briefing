import os
import re
import feedparser, anthropic, requests, datetime

CLAUDE_API_KEY   = os.environ.get("CLAUDE_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

RSS_FEEDS = [
    {"name": "eVTOL News",    "url": "https://evtol.news/__rss"},
    {"name": "Simple Flying", "url": "https://simpleflying.com/feed"},
    {"name": "Vertical Mag",  "url": "https://verticalmag.com/feed"},
    {"name": "Aviation Week", "url": "https://aviationweek.com/rss.xml"},
    {"name": "FAA News",      "url": "https://www.federalregister.gov/api/v1/documents.rss?conditions%5Bagencies%5D%5B%5D=federal-aviation-administration"},
    {"name": "EASA News",     "url": "https://www.easa.europa.eu/en/newsroom-and-events/news/feed.xml"},
    {"name": "AVweb",        "url": "https://avweb.com/feed/"},
]

def collect_news():
    articles = []
    for f in RSS_FEEDS:
        try:
            feed = feedparser.parse(f["url"])
            for e in feed.entries[:3]:
                articles.append({"source": f["name"], "title": e.get("title",""), "summary": e.get("summary", e.get("description",""))[:400], "link": e.get("link","")})
            print(f"✅ {f['name']}: {min(3,len(feed.entries))}개")
        except Exception as ex:
            print(f"⚠️ {f['name']} 실패: {ex}")
    return articles

def _filter_stale_urls(urls, max_age_days=21):
    now = datetime.datetime.utcnow()
    pattern = re.compile(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})")
    kept = []
    for u in urls:
        m = pattern.search(u)
        if m:
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dt = datetime.datetime(y, mo, d)
                if (now - dt).days > max_age_days:
                    continue
            except ValueError:
                pass
        kept.append(u)
    return kept

RAIL_KEYWORDS = ["철도", "지하철", "KTX", "전동차", "열차"]

def _strip_rail_content(text):
    lines = text.split("\n")
    kept = [ln for ln in lines if not any(k in ln for k in RAIL_KEYWORDS)]
    return "\n".join(kept)

def web_search(client, query, max_uses=3, max_age_days=10):
    def _call(q):
        msg = client.messages.create(model="claude-haiku-4-5", max_tokens=1200,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}],
            messages=[{"role":"user","content":q}])
        text_parts = []
        urls = []
        for b in msg.content:
            if hasattr(b, "text"):
                text_parts.append(b.text)
            for c in (getattr(b, "citations", None) or []):
                u = getattr(c, "url", None)
                t = getattr(c, "title", None)
                if u:
                    urls.append(f"{t or ''} - {u}".strip(" -"))
        out = "".join(text_parts)
        uniq = list(dict.fromkeys(urls))
        uniq = _filter_stale_urls(uniq, max_age_days=max_age_days)
        if uniq:
            out += "\n\n[실제 출처 링크]\n" + "\n".join(uniq[:10])
        return out
    result = _call(query)
    refusal_markers = ["구체적인 질문", "명확화", "질문이 필요", "무엇을 원하시", "어떤 정보를 찾으", "다시 말씀", "clarif", "more specific"]
    if any(m in result for m in refusal_markers) or len(result.strip()) < 20:
        print("   ⚠️ 검색 결과가 거절/빈 응답처럼 보여 1회 재시도")
        result = _call(query + "\n\n다시 한번 강조: 절대 질문하거나 명확화를 요구하지 말고, 위에 나열된 키워드들로 지금 바로 web_search 도구를 호출해서 실제 검색 결과를 요약해. 텍스트로만 답하지 말고 반드시 도구를 사용해.")
    return result

SEARCH_CATEGORIES = [
    ("글로벌 항공산업 주요 뉴스",
     "너는 지금 web_search 도구를 실제로 호출해서 검색을 수행해야 해. 절대 질문하거나 명확화를 요구하지 마. 최근 48시간, 부족하면 최근 7일 이내의 글로벌 상업항공·항공산업 전반 주요 뉴스를 검색해서 요약해줘. 단순 신규노선 프로모션이나 주가·실적 뉴스는 제외하고, 실제 발생일/발표일이 확인되는 뉴스만 요약해."),
    ("항공기 개발 제작 엔진 부품 MRO",
     "너는 지금 web_search 도구를 실제로 호출해서 검색을 수행해야 해. 절대 질문하거나 명확화를 요구하지 마. 최근 48시간, 부족하면 최근 7일 이내 항공기 개발·제작, 엔진·추진시스템, 항공전자·소프트웨어, 부품·공급망, MRO·계속감항성 관련 뉴스를 검색해서 요약해줘. 실제 발생일/발표일을 함께 확인해."),
    ("항공안전 사고",
     "너는 지금 web_search 도구를 실제로 호출해서 검색을 수행해야 해. 절대 질문하거나 명확화를 요구하지 마. NTSB(ntsb.gov) 등 공식 조사기관 자료를 우선해서, 최근 48시간~7일 이내 전세계 항공안전·사고·조사 관련 뉴스를 검색해서 요약해줘. 조사 중인 사고의 원인을 단정하지 말고 사실만 정리해."),
    ("FAA 인증 감항 규제",
     "너는 지금 web_search 도구를 실제로 호출해서 검색을 수행해야 해. 절대 질문하거나 명확화를 요구하지 마. faa.gov와 federalregister.gov에서 최근 7일 이내 새로 나온 Airworthiness Directive, Final Rule, NPRM/Proposed Rule, Notice, Advisory Circular, Part 21/23/25/27/29, Powered-Lift/UAS 관련 규제 문서를 검색해서 문서명·상태(AD/Final Rule/NPRM 등)·발행일·핵심내용을 요약해줘."),
    ("EASA 인증 감항 규제",
     "너는 지금 web_search 도구를 실제로 호출해서 검색을 수행해야 해. 절대 질문하거나 명확화를 요구하지 마. easa.europa.eu에서 최근 7일 이내 새로 나온 Airworthiness Directive, NPA, ED Decision, CS/AMC/GM 개정 등 규제 문서를 검색해서 문서명·상태·발행일·핵심내용을 요약해줘."),
    ("UAS 드론 UAM eVTOL",
     "너는 지금 web_search 도구를 실제로 호출해서 검색을 수행해야 해. 절대 질문하거나 명확화를 요구하지 마. 최근 48시간~7일 이내 전세계 UAS·드론·UAM·eVTOL 관련 뉴스를 검색해서 요약해줘. UAM에만 편중하지 말고 UAS/드론 관련 소식도 균형있게 포함해."),
    ("대한민국 항공산업",
     "너는 지금 web_search 도구를 실제로 호출해서 검색을 수행해야 해. 절대 질문하거나 명확화를 요구하지 마. 최근 48시간~7일 이내 대한민국 항공산업·항공기업(KAI, 한화에어로스페이스, 대한항공, 아시아나 등)·공항·항공사·국내 항공기/UAS/UAM 개발 관련 뉴스를 검색해서 요약해줘. 한국 언론이 보도했더라도 해외에서 일어난 사건은 국내 뉴스가 아니니 제외해."),
    ("대한민국 항공인증 감항 정책 규제",
     "너는 지금 web_search 도구를 실제로 호출해서 검색을 수행해야 해. 절대 질문하거나 명확화를 요구하지 마. 국토교통부, 국가법령정보센터(law.go.kr), 항공철도사고조사위원회, 항공안전기술원, 우주항공청, 방위사업청에서 최근 7일 이내 항공안전법·시행령·시행규칙·항공기술기준·고시·훈령·입법예고·행정예고 등 인증·감항 관련 제도 변경을 검색해서 요약해줘. 철도·지하철 관련 내용은 검색 대상이 아니니 제외해."),
]

def run_category_searches(client):
    results = []
    for name, q in SEARCH_CATEGORIES:
        print(f"🔍 검색: {name}")
        domestic = name.startswith("대한민국")
        r = web_search(client, q, max_uses=3)
        if domestic:
            r = _strip_rail_content(r)
        results.append((name, r))
    return results

def format_research_data(results):
    parts = [f"[{name}]\n{text}" for name, text in results]
    return "\n\n".join(parts)

def send(text):
    max_len = 4000
    parts = []
    while len(text) > max_len:
        idx = text[:max_len].rfind("\n")
        if idx == -1: idx = max_len
        parts.append(text[:idx])
        text = text[idx:].strip()
    parts.append(text)
    for i, part in enumerate(parts):
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": part, "parse_mode": "Markdown"})
        if r.status_code != 200:
            r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": part})
        print(f"✅ {i+1}/{len(parts)} 발송 완료!" if r.status_code==200 else f"❌ 실패: {r.text}")

BRIEFING_RULES = """[가장 중요한 원칙]
- 제공된 데이터에 실제 존재하는 사실만 사용한다. 없는 사실을 추정하거나 만들어내지 않는다.
- 기사 수를 채우기 위해 중요도가 낮거나 오래된 자료를 쓰지 않는다.
- 사실과 해석을 명확히 구분한다.
- 공식 규제기관 자료와 일반 뉴스가 충돌하면 공식 자료를 우선한다.
- 사고·결함·인증·규제 관련 내용은 특히 보수적으로 작성한다.

[날짜 검증 — 반드시 수행]
1) 실제 사건 발생일 또는 공식 발표일을 확인한다.
2) 브리핑 기준일과의 날짜 차이를 계산한다.
3) 0~2일: 우선 선정 가능. 4) 3~7일: 중요도가 높은 경우에만 선정. 5) 8일 이상: 무조건 제외. 6) 발생일/발표일을 확인할 수 없는 자료: 제외.
- 최근에 작성된 기사라도 과거 사건을 다시 다룬 기사면 오늘의 뉴스에서 제외한다.
- 과거에 발표된 정책의 목표연도가 미래라는 이유만으로 최신 뉴스로 선정하지 않는다.
- 미래 일정은 "예정", "계획"으로 표현하고 이미 발생한 것처럼 쓰지 않는다.
- 해외·국내 각각 최대 3건이며 반드시 채울 필요는 없다.
- 적합한 국내 뉴스가 없으면 "최근 7일 이내 별도의 주요 국내 항공산업 이슈는 확인되지 않았습니다."라고 쓴다.

[국내 뉴스 판정]
- 한국어로 작성된 기사라는 이유만으로 국내 뉴스로 분류하지 않는다. 대한민국 항공산업/기업/정부기관/공항·항공사/국내 항공기·UAS·UAM 개발/국내 항공안전 사건/국내 항공인증·감항·규제/국내 항공부품·제조·MRO/국내 항공 R&D·실증사업 중 하나 이상을 직접 다룰 때만 국내 뉴스다. 한국 언론이 보도한 해외 사건은 해외 뉴스다.

[사고·결함 관련 추정 금지]
- 조사 중인 사고나 결함의 원인을 임의로 판단하지 않는다. "설계 결함/제조 결함/구조 결함/소프트웨어 결함/정비 불량/인증 실패"는 공식 조사에서 확인되지 않았으면 쓰지 않는다.
- 사고·결함이 발생했다는 이유만으로 AD/SB 발행, 추가 검사, 인증 변경, 재인증, 재형식증명, 추가 시험을 예상하지 않는다. "AD로 이어질 수 있다"류의 추측 문장을 쓰지 않는다. FAA/EASA/제조사/공식 조사기관이 실제로 발표한 경우에만 작성한다.

[인증·감항 용어 정확성]
- TC=형식증명, STC=부가형식증명, AD=감항성개선지시, MoC=적합성 입증방법, CCL=Compliance Checklist, FHA=Functional Hazard Assessment.
- 형식증명과 감항증명을 동일하게 쓰지 않는다. 시험 성공을 인증 완료로 표현하지 않는다. 특정 항공기에 승인된 기술을 다른 기종·산업 전체로 확대 해석하지 않는다. 군용 UAS 시험 문제를 민간 FAA/EASA 인증체계와 자동으로 연결하지 않는다.

[규제 정보]
- 최근 7일 이내 공식 데이터에서 새로운 AD/Final Rule/NPRM/NPA/ED Decision/CS·AMC·GM 개정/AC/국내 법령·행정규칙 변경이 확인되면 일반 뉴스보다 우선한다. 단순 행정공지·채용·조직공지는 제외한다.
- NPRM/NPA/입법예고/행정예고는 확정 규정처럼 표현하지 않는다. 발행일·공포일·시행일·의견수렴 마감일을 구분한다. 규정 번호·AC 번호·CS 번호·표준 번호·시행일을 데이터에서 직접 확인할 수 없으면 만들어내지 않는다. 웹페이지 수정일/검색일을 발표일로 오인하지 않는다.

[AW 인증·산업 관점]
- 모든 뉴스를 억지로 인증과 연결하지 않는다. 인증·감항·안전·개발과 직접 관련된 가장 중요한 1~2개 이슈만 3~5문장으로 분석한다. 기사에 없는 인증기관·절차·시험·재인증 필요성을 만들어내지 않는다.

[헤드라인]
- 가장 강한 뉴스 1건만 헤드라인으로 쓴다. 서로 다른 뉴스 2개를 하나로 묶지 않는다. 기사 제목을 그대로 번역하지 말고 질문형/문제제기형을 우선한다. 항공기명·엔진명·수량·인증·규제 변화 등 구체적 팩트를 포함한다. 과장·낚시성 표현 금지. 35자 이내.

[문체]
- 비전문가도 이해할 수 있되 실무자가 읽어도 부정확하지 않게 쓴다. "획기적/역사적/혁신적/최초/안전성을 보장/업계 판도를 바꾼다" 등은 객관적 근거가 있을 때만 쓴다. "안전성을 높일 수 있다"와 "안전성을 보장한다"를 구분한다.

[출력 전 최종 자체검증]
출력 직전 다음을 내부 확인하고, 하나라도 위반하면 해당 문장/뉴스를 삭제하거나 수정한 뒤 출력한다:
8일 이상 지난 뉴스 포함 여부 / 과거 정책을 최신처럼 표현했는지 / 미래 일정을 완료된 것처럼 썼는지 / 해외 뉴스를 국내로 분류했는지 / 사고 원인을 추정했는지 / AD·SB·재인증을 임의로 예상했는지 / NPRM·NPA를 확정 규정으로 썼는지 / 형식증명과 감항증명을 혼동했는지 / 규정번호·날짜를 만들어냈는지 / 기사 수를 맞추려 중요하지 않은 뉴스를 넣었는지 / 공식 규제자료보다 일반 기사를 우선했는지.

- 각 뉴스와 규제 업데이트에는 가능하면 실제 확인한 원문 링크를 함께 제공한다."""

def main():
    KST = datetime.timezone(datetime.timedelta(hours=9))
    now_kst = datetime.datetime.now(KST)
    print("="*50)
    print(f"AW항공 데일리 브리핑 | {now_kst.strftime('%Y-%m-%d %H:%M')} KST")
    print("="*50)
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    today = now_kst.strftime("%Y년 %m월 %d일")
    articles = collect_news()
    news_text = "\n".join([f"[{a['source']}] {a['title']}\n{a['summary']}\n{a['link']}" for a in articles])
    print(f"\n총 {len(articles)}개 기사 수집")

    category_results = run_category_searches(client)
    research_data = format_research_data(category_results)
    print(f"   리서치 데이터 미리보기: {research_data[:150]!r}")

    print("✍️ AW항공브리핑 작성 중...")
    m1 = client.messages.create(model="claude-haiku-4-5", max_tokens=4500,
        messages=[{"role":"user","content":f"당신은 AW인증솔루션의 항공산업·항공인증 데일리 브리핑 전문 에디터입니다. 제공된 뉴스 데이터와 FAA·EASA·대한민국 공식 규제 데이터를 검토하여 기준일({today}) 현재의 'AW항공브리핑'을 한국어로 작성하세요. 목표는 단순 뉴스 요약이 아니라 항공산업 관계자가 오늘 알아야 할 중요한 산업·안전·인증·규제 변화를 정확하고 이해하기 쉽게 전달하는 것입니다. 너의 실시간 인터넷 접속 여부는 언급하지 말고 아래 자료만 근거로 작성해.\n\n{BRIEFING_RULES}\n\n[RSS 배경자료]\n{news_text}\n\n[카테고리별 리서치 데이터]\n{research_data}\n\n형식:\n✈️ *[오늘의 핵심 헤드라인]*\n*AW항공브리핑 | {today}*\n\n오늘 주목할 국내외 항공산업 주요 소식을 정리했습니다.\n\n🌎 *해외 주요 동향*\n\n*[뉴스 1]*\n2~3문장\n\n*[뉴스 2]*\n2~3문장\n\n(최대 3건)\n\n🇰🇷 *국내 주요 동향*\n\n동일한 방식으로 최대 3건, 없으면 '최근 7일 이내 별도의 주요 국내 항공산업 이슈는 확인되지 않았습니다.'\n\n📑 *인증·규제 업데이트*\n(최근 중요 변경사항이 있을 때만, 없는 기관은 생략)\n\n🇺🇸 FAA | [문서명]\n상태:\n핵심 변경:\n적용 대상:\n주요 날짜:\n\n🇪🇺 EASA | [문서명]\n상태:\n핵심 변경:\n적용 대상:\n주요 날짜:\n\n🇰🇷 대한민국 | [문서명]\n상태:\n핵심 변경:\n적용 대상:\n주요 날짜:\n\n중요한 변경사항이 전혀 없으면: '최근 7일 이내 별도의 주요 인증·규제 변경사항은 확인되지 않았습니다.'\n\n🔎 *AW 인증·산업 관점*\n가장 중요한 1~2개 이슈만 총 3~5문장으로\n\n📌 *오늘의 한 줄*\n브리핑 전체를 한 문장으로\n\n_AW인증솔루션 | awcertsolution.kr_\n\n#항공 #항공산업 #항공인증 #감항인증 #FAA #EASA"}])

    print("🎬 숏폼 소재 후보 작성 중...")
    m3 = client.messages.create(model="claude-haiku-4-5", max_tokens=2000,
        messages=[{"role":"user","content":f"항공 인증 콘텐츠 크리에이터. 오늘 날짜는 {today}야. 아래 [뉴스]/[카테고리별 리서치 데이터] 자료를 검토해서 숏폼 영상이나 카드뉴스로 만들기 좋은 소재를 골라줘. 자료에 없는 내용은 추측하지 마. 특히 규격 번호·문서 버전·정확한 날짜처럼 구체적인 숫자나 명칭은 자료에 그대로 나와있지 않으면 절대 만들어내지 말고 뭉뚱그려 표현해. 소재로 고를 뉴스는 반드시 최근 2주 이내에 실제로 발생하거나 발표된 것만 선택하고, 그보다 오래된 기사나 날짜가 불분명한 자료는 절대 소재로 쓰지 마. 각 소재의 소재 설명에는 구체적인 날짜(예: 2026년 9월 X일 또는 최소 '이번 주')를 반드시 명시해. 아래 5개 콘텐츠 유형 중 가장 잘 맞는 것 하나로 소재를 분류해줘(억지로 끼워맞추지 말 것):\n1) 항공사업 진입 숏폼 - 타깃:연구소장·임원, 예:자동차 부품회사가 항공사업을 시작할 때 놓치는 것, CTA:인증 준비도 진단\n2) 개발·인증 문제 숏폼 - 타깃:개발팀장·PM, 예:시험은 했는데 인증자료가 부족한 이유, CTA:컨설팅 상담\n3) 실무 문제해결 숏폼 - 타깃:개발 엔지니어, 예:DO-160 시험 전 확인해야 할 것, CTA:전자책 다운로드\n4) 항공인증 용어사전 - 타깃:주니어 연구원, 예:CCL, FHA, MoC, DAL, CTA:전자책·클래스101\n5) 5분 교육 미드폼 - 타깃:개발팀장·실무자, 예:항공기 인증계획서 작성 흐름, CTA:기업교육·컨설팅\n\n선정 기준: 1) 후킹력 있는 소재(반전, 놀라운 사실, 논란, 사고), 2) 시각 자료(영상·사진)가 있을 법한 소재, 3) 위 5개 유형 중 하나에 명확히 들어맞는 소재. 최대 3개까지만 선정하고, 마땅한 소재가 전혀 없으면 다른 말 없이 '오늘은 특별한 소재가 없습니다'라고만 답해.\n\n[뉴스]\n{news_text}\n\n[카테고리별 리서치 데이터]\n{research_data}\n\n형식:\n🎬 *숏폼/카드뉴스 소재 후보 | {today}*\n\n1️⃣ *[후킹 한 줄 제목]*\n📍 소재: 무슨 일이 있었는지 2~3문장\n🎯 콘텐츠 유형: [5개 유형 중 하나] | 타깃: [해당 타깃]\n💡 왜 소재로 좋은지: 반전·놀라움·논란 포인트 1문장\n🎥 형식 제안: 숏폼 영상 또는 카드뉴스 중 추천 + 이유 1문장\n📣 다음 행동: [해당 CTA]\n🔗 출처: 자료의 [실제 출처 링크] 목록에 있는 URL을 그대로 복사, 없으면 '링크 확인 필요'라고 표시\n\n(소재가 더 있으면 2️⃣ 3️⃣로 이어서, 최대 3개)"}])

    send(m1.content[0].text)
    send(m3.content[0].text)
    print("\n🎉 완료!")

if __name__ == "__main__":
    main()
