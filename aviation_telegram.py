import os
import feedparser, anthropic, requests, datetime

CLAUDE_API_KEY   = os.environ.get("CLAUDE_API_KEY")
TELEGRAM_TOKEN   = "8385206243:AAHvdOIMBkknpJLl83iiPf8RZYHRK09sS5U"
TELEGRAM_CHAT_ID = "8909776847"

RSS_FEEDS = [
    {"name": "eVTOL News",    "url": "https://evtol.news/feed"},
    {"name": "Simple Flying", "url": "https://simpleflying.com/feed"},
    {"name": "Vertical Mag",  "url": "https://verticalmag.com/feed"},
    {"name": "Aviation Week", "url": "https://aviationweek.com/rss.xml"},
    {"name": "FAA News",      "url": "https://www.faa.gov/rss/news_updates.xml"},
    {"name": "EASA News",     "url": "https://www.easa.europa.eu/en/rss.xml"},
    {"name": "AIN Online",    "url": "https://www.ainonline.com/rss.xml"},
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

def web_search(client, query, max_uses=3):
    msg = client.messages.create(model="claude-haiku-4-5", max_tokens=1000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}],
        messages=[{"role":"user","content":query}])
    return "".join(b.text for b in msg.content if hasattr(b, "text"))

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
def main():
    print("="*50)
    print(f"AW항공 데일리 브리핑 | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*50)
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    today = datetime.datetime.now().strftime("%Y년 %m월 %d일")
    articles = collect_news()
    news_text = "\n".join([f"[{a['source']}] {a['title']}\n{a['summary']}\n{a['link']}" for a in articles])
    print(f"\n총 {len(articles)}개 기사 수집")
    print("🔍 해외 항공 정보 검색 중...")
    global_search = web_search(client, "Search for latest FAA EASA aviation certification rule changes Advisory Circulars UAM eVTOL regulatory updates this week 2026")
    print("🔍 국내 항공 정보 검색 중...")
    korea_search = web_search(client, "2026년 대한민국 UAM eVTOL 항공부품 인증 정부과제 공고 국토부 방사청 산업부 중기부 경남 부산 대구 인천 서울 경기 지자체 항공 UAM 사업공고 K-UAM 그랜드챌린지 NTIS IRIS 항공인증 과제공고", max_uses=6)
    print("✍️ 해외 브리핑 작성 중...")
    m1 = client.messages.create(model="claude-haiku-4-5", max_tokens=3200,
                messages=[{"role":"user","content":f"항공 인증 전문가. 오늘({today}) 해외 항공 뉴스 텔레그램 메시지 작성. 구체적 사실 기반. 각 섹션은 먼저 핵심 사실을 불릿(•)으로 2~3개 정리하고, 그 아래에 짧은 줄글로 1~2문장 부연 설명을 붙여줘. 전문용어가 처음 나올 때는 괄호로 짧게 풀어써줘. 가능하면 출처 링크를 표시해줘.\n\n[RSS]\n{news_text}\n\n[웹검색]\n{global_search}\n\n형식:\n✈️ *AW항공브리핑 해외편 | {today}*\n[오늘 가장 중요한 소식을 임팩트 있게 한 줄로 요약한 후킹 헤드라인]\n\n📌 *핵심 요약*\n• 불릿1\n• 불릿2\n• 불릿3\n\n💡 *쉽게 이해하기*\n전문용어 없이 왜 중요한지 2~3문장으로 풀어서 설명\n\n🚁 *UAM eVTOL 글로벌 동향*\n• 불릿1\n• 불릿2\n줄글 1~2문장\n\n📋 *FAA EASA 인증 변화*\n• 불릿1\n• 불릿2\n줄글 1~2문장\n\n💼 *글로벌 비즈니스 투자*\n• 불릿1\n• 불릿2\n줄글 1문장\n\n📓 *용어 정리*\n▷ 용어1: 짧은 설명\n▷ 용어2: 짧은 설명\n\n📈 *앞으로 지켜볼 것*\n① 포인트1\n② 포인트2\n③ 포인트3\n\n💬 *결론적으로*\n1~2문장으로 종합 정리\n\n🔗 *원문 링크*\n있으면 링크 나열, 없으면 이 섹션 생략\n\n_AW인증솔루션_"}])
    print("✍️ 국내 브리핑 작성 중...")
    m2 = client.messages.create(model="claude-haiku-4-5", max_tokens=3200,
                        messages=[{"role":"user","content":f"항공 인증 전문가. 오늘({today}) 국내 항공 동향 텔레그램 메시지 작성. 구체적 사실 기반. 각 섹션은 먼저 핵심 사실을 불릿(•)으로 2~3개 정리하고, 그 아래에 짧은 줄글로 1~2문장 부연 설명을 붙여줘. 전문용어가 처음 나올 때는 괄호로 짧게 풀어써줘. 가능하면 출처 링크를 표시해줘.\n\n[웹검색]\n{korea_search}\n\n형식:\n🇰🇷 *AW항공브리핑 국내편 | {today}*\n[오늘 가장 중요한 소식을 임팩트 있게 한 줄로 요약한 후킹 헤드라인]\n\n📌 *핵심 요약*\n• 불릿1\n• 불릿2\n• 불릿3\n\n💡 *쉽게 이해하기*\n전문용어 없이 왜 중요한지 2~3문장으로 풀어서 설명\n\n🏛️ *국토부 방사청 정책 동향*\n• 불릿1\n• 불릿2\n줄글 1~2문장\n\n📢 *정부 지자체 과제 공고*\n• 과제명 및 내용\n• 과제명 및 내용\n\n🗺️ *지자체 항공 UAM 사업*\n• 지자체1 내용\n• 지자체2 내용\n\n📓 *용어 정리*\n▷ 용어1: 짧은 설명\n▷ 용어2: 짧은 설명\n\n📈 *앞으로 지켜볼 것*\n① 포인트1\n② 포인트2\n③ 포인트3\n\n💬 *결론적으로*\n1~2문장으로 종합 정리, 국내 기업에게 시사점 포함\n\n🔗 *원문 링크*\n있으면 링크 나열, 없으면 이 섹션 생략\n\n_AW인증솔루션 | awcertsolution.kr_"}])
    send(m1.content[0].text)
    send(m2.content[0].text)
    print("\n🎉 완료!")

if __name__ == "__main__":
    main()
