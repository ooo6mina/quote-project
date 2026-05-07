from fastapi import FastAPI, HTTPException
from sqlmodel import SQLModel, Field, Session, create_engine, select
from bs4 import BeautifulSoup
import requests
import gradio as gr
import pandas as pd
import matplotlib.pyplot as plt
from collections import Counter
import re
from wordcloud import WordCloud

# ======================================================
# DATABASE MODEL
# ======================================================

class QuoteBase(SQLModel):
    text: str
    author: str
    tags: str = ""
    category: str = ""

class Quote(QuoteBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

class QuoteCreate(QuoteBase):
    pass

class QuoteUpdate(SQLModel):
    text: str | None = None
    author: str | None = None
    tags: str | None = None
    category: str | None = None


# ======================================================
# DATABASE SETTING
# ======================================================

engine = create_engine(
    "sqlite:///quotes.db",
    connect_args={"check_same_thread": False}
)

def create_db():
    SQLModel.metadata.create_all(engine)


# ======================================================
# CRAWLER
# ======================================================

def crawl_quotes_by_category(category: str, limit: int = 20):

    base_url = "https://quotes.toscrape.com"
    url = f"{base_url}/tag/{category}/"

    result = []

    while url and len(result) < limit:

        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            break

        soup = BeautifulSoup(response.text, "html.parser")

        quote_items = soup.select(".quote")

        if not quote_items:
            break

        for item in quote_items:

            text = item.select_one(".text").get_text(strip=True)

            author = item.select_one(".author").get_text(strip=True)

            tags = ",".join(
                tag.get_text(strip=True)
                for tag in item.select(".tag")
            )

            result.append({
                "text": text,
                "author": author,
                "tags": tags,
                "category": category
            })

            if len(result) >= limit:
                break

        next_btn = soup.select_one(".next a")

        url = (
            base_url + next_btn["href"]
            if next_btn else None
        )

    return result


# ======================================================
# FASTAPI
# ======================================================

app = FastAPI(
    title="FastAPI 기반 격언 관리 및 분석 시스템",
    description="""
    BeautifulSoup 기반 크롤링,
    SQLite 데이터베이스 저장,
    FastAPI CRUD API,
    Swagger UI,
    Gradio 통합 UI,
    통계 및 시각화 기능 제공
    """,
    version="1.0.0"
)

@app.on_event("startup")
def on_startup():
    create_db()

@app.get("/")
def home():
    return {
        "project": "Quote Management System",
        "docs": "/docs",
        "gradio": "/gradio",
        "features": [
            "Category Crawling",
            "SQLite Database",
            "FastAPI CRUD",
            "Swagger UI",
            "Gradio Dashboard",
            "Word Frequency Analysis",
            "Author Statistics",
            "Tag Statistics",
            "WordCloud"
        ]
    }


# ======================================================
# CRAWL API
# ======================================================

@app.post("/crawl/{category}")
def crawl_and_save(category: str, limit: int = 20):

    quotes = crawl_quotes_by_category(category, limit)

    if not quotes:
        raise HTTPException(
            status_code=404,
            detail="No quotes found"
        )

    saved_count = 0

    with Session(engine) as session:

        for q in quotes:

            exists = session.exec(
                select(Quote).where(
                    Quote.text == q["text"]
                )
            ).first()

            if not exists:
                session.add(Quote(**q))
                saved_count += 1

        session.commit()

    return {
        "category": category,
        "crawled": len(quotes),
        "saved": saved_count,
        "message": "Crawling completed"
    }


# ======================================================
# CRUD API
# ======================================================

@app.post("/quotes", response_model=Quote)
def create_quote(quote: QuoteCreate):

    with Session(engine) as session:

        db_quote = Quote.model_validate(quote)

        session.add(db_quote)

        session.commit()

        session.refresh(db_quote)

        return db_quote


@app.get("/quotes", response_model=list[Quote])
def read_quotes():

    with Session(engine) as session:

        quotes = session.exec(
            select(Quote)
        ).all()

        return quotes


@app.get("/quotes/{quote_id}", response_model=Quote)
def read_quote(quote_id: int):

    with Session(engine) as session:

        quote = session.get(Quote, quote_id)

        if not quote:
            raise HTTPException(
                status_code=404,
                detail="Quote not found"
            )

        return quote


@app.put("/quotes/{quote_id}", response_model=Quote)
def update_quote(
    quote_id: int,
    quote_update: QuoteUpdate
):

    with Session(engine) as session:

        quote = session.get(Quote, quote_id)

        if not quote:
            raise HTTPException(
                status_code=404,
                detail="Quote not found"
            )

        update_data = quote_update.model_dump(
            exclude_unset=True
        )

        for key, value in update_data.items():
            setattr(quote, key, value)

        session.add(quote)

        session.commit()

        session.refresh(quote)

        return quote


@app.delete("/quotes/{quote_id}")
def delete_quote(quote_id: int):

    with Session(engine) as session:

        quote = session.get(Quote, quote_id)

        if not quote:
            raise HTTPException(
                status_code=404,
                detail="Quote not found"
            )

        session.delete(quote)

        session.commit()

        return {
            "message": "Quote deleted successfully"
        }


# ======================================================
# HELPER FUNCTIONS
# ======================================================

def get_all_quotes_df():

    with Session(engine) as session:

        quotes = session.exec(
            select(Quote)
        ).all()

    if not quotes:
        return pd.DataFrame(
            columns=[
                "id",
                "text",
                "author",
                "tags",
                "category"
            ]
        )

    return pd.DataFrame(
        [q.model_dump() for q in quotes]
    )


# ======================================================
# GRADIO FUNCTIONS
# ======================================================

def ui_crawl(category, limit):

    data = crawl_quotes_by_category(
        category,
        int(limit)
    )

    if not data:
        return (
            "데이터가 없습니다.",
            get_all_quotes_df()
        )

    saved = 0

    with Session(engine) as session:

        for q in data:

            exists = session.exec(
                select(Quote).where(
                    Quote.text == q["text"]
                )
            ).first()

            if not exists:
                session.add(Quote(**q))
                saved += 1

        session.commit()

    return (
        f"{category} 카테고리 "
        f"{saved}개 저장 완료",
        get_all_quotes_df()
    )


def ui_list_quotes():
    return get_all_quotes_df()


def ui_create_quote(
    text,
    author,
    tags,
    category
):

    if not text or not author:
        return (
            "내용과 작가는 필수입니다.",
            get_all_quotes_df()
        )

    with Session(engine) as session:

        quote = Quote(
            text=text,
            author=author,
            tags=tags,
            category=category
        )

        session.add(quote)

        session.commit()

    return (
        "추가 완료",
        get_all_quotes_df()
    )


def ui_update_quote(
    quote_id,
    text,
    author,
    tags,
    category
):

    with Session(engine) as session:

        quote = session.get(
            Quote,
            int(quote_id)
        )

        if not quote:
            return (
                "해당 ID 없음",
                get_all_quotes_df()
            )

        quote.text = text
        quote.author = author
        quote.tags = tags
        quote.category = category

        session.add(quote)

        session.commit()

    return (
        "수정 완료",
        get_all_quotes_df()
    )


def ui_delete_quote(quote_id):

    with Session(engine) as session:

        quote = session.get(
            Quote,
            int(quote_id)
        )

        if not quote:
            return (
                "해당 ID 없음",
                get_all_quotes_df()
            )

        session.delete(quote)

        session.commit()

    return (
        "삭제 완료",
        get_all_quotes_df()
    )


# ======================================================
# ANALYSIS
# ======================================================

def word_count_chart():

    df = get_all_quotes_df()

    if df.empty:
        return None

    text = " ".join(
        df["text"].tolist()
    ).lower()

    words = re.findall(
        r"[a-zA-Z]+",
        text
    )

    stopwords = {
        "the", "and", "is", "to", "of",
        "a", "in", "that", "it", "you",
        "i", "for", "on", "with", "as",
        "are", "be", "not"
    }

    words = [
        w for w in words
        if w not in stopwords and len(w) > 2
    ]

    counter = Counter(words).most_common(10)

    words_df = pd.DataFrame(
        counter,
        columns=["word", "count"]
    )

    fig, ax = plt.subplots()

    ax.bar(
        words_df["word"],
        words_df["count"]
    )

    ax.set_title("Top 10 Word Frequency")

    ax.set_xlabel("Word")

    ax.set_ylabel("Count")

    plt.xticks(rotation=45)

    return fig


def author_chart():

    df = get_all_quotes_df()

    if df.empty:
        return None

    counts = (
        df["author"]
        .value_counts()
        .head(10)
    )

    fig, ax = plt.subplots()

    ax.bar(
        counts.index,
        counts.values
    )

    ax.set_title("Top Authors")

    ax.set_xlabel("Author")

    ax.set_ylabel("Quote Count")

    plt.xticks(rotation=45)

    return fig


def tag_chart():

    df = get_all_quotes_df()

    if df.empty:
        return None

    tags = []

    for tag_text in df["tags"]:

        tags.extend([
            tag.strip()
            for tag in tag_text.split(",")
            if tag.strip()
        ])

    counts = Counter(tags).most_common(10)

    tag_df = pd.DataFrame(
        counts,
        columns=["tag", "count"]
    )

    fig, ax = plt.subplots()

    ax.bar(
        tag_df["tag"],
        tag_df["count"]
    )

    ax.set_title("Top Tags")

    ax.set_xlabel("Tag")

    ax.set_ylabel("Count")

    plt.xticks(rotation=45)

    return fig


def wordcloud_chart():

    df = get_all_quotes_df()

    if df.empty:
        return None

    text = " ".join(
        df["text"].tolist()
    )

    wc = WordCloud(
        width=800,
        height=400,
        background_color="white"
    ).generate(text)

    fig, ax = plt.subplots()

    ax.imshow(wc)

    ax.axis("off")

    ax.set_title("WordCloud")

    return fig


def summary_stats():

    df = get_all_quotes_df()

    if df.empty:

        return pd.DataFrame({
            "metric": [
                "total_quotes",
                "authors",
                "categories",
                "tags"
            ],
            "value": [0, 0, 0, 0]
        })

    all_tags = []

    for tag_text in df["tags"]:

        all_tags.extend([
            tag.strip()
            for tag in tag_text.split(",")
            if tag.strip()
        ])

    return pd.DataFrame({
        "metric": [
            "total_quotes",
            "authors",
            "categories",
            "unique_tags"
        ],
        "value": [
            len(df),
            df["author"].nunique(),
            df["category"].nunique(),
            len(set(all_tags))
        ]
    })


# ======================================================
# GRADIO UI
# ======================================================

with gr.Blocks(
    title="격언 관리 및 분석 시스템"
) as demo:

    gr.Markdown("""
    # FastAPI 기반 격언 관리 및 분석 시스템

    ## 기능
    - 카테고리별 격언 크롤링
    - SQLite 저장
    - FastAPI CRUD API
    - Swagger UI
    - Gradio 통합 서비스
    - 단어 빈도 분석
    - 작가 통계
    - 태그 통계
    - 워드클라우드
    """)

    # =====================================
    # CRAWL
    # =====================================

    with gr.Tab("1. 카테고리별 크롤링"):

        category_input = gr.Dropdown(
            choices=[
                "life",
                "love",
                "inspirational",
                "humor",
                "books",
                "reading",
                "friendship",
                "truth"
            ],
            value="life",
            label="카테고리"
        )

        limit_input = gr.Slider(
            minimum=1,
            maximum=20,
            value=20,
            step=1,
            label="수집 개수"
        )

        crawl_btn = gr.Button(
            "크롤링 후 DB 저장"
        )

        crawl_msg = gr.Textbox(
            label="결과"
        )

        crawl_table = gr.Dataframe(
            label="저장 데이터"
        )

        crawl_btn.click(
            ui_crawl,
            inputs=[
                category_input,
                limit_input
            ],
            outputs=[
                crawl_msg,
                crawl_table
            ]
        )

    # =====================================
    # READ
    # =====================================

    with gr.Tab("2. 전체 조회"):

        list_btn = gr.Button(
            "전체 조회"
        )

        list_table = gr.Dataframe(
            label="Quotes Table"
        )

        list_btn.click(
            ui_list_quotes,
            outputs=list_table
        )

    # =====================================
    # CREATE
    # =====================================

    with gr.Tab("3. 격언 추가"):

        create_text = gr.Textbox(
            label="격언 내용"
        )

        create_author = gr.Textbox(
            label="작가"
        )

        create_tags = gr.Textbox(
            label="태그"
        )

        create_category = gr.Textbox(
            label="카테고리"
        )

        create_btn = gr.Button(
            "추가"
        )

        create_msg = gr.Textbox(
            label="결과"
        )

        create_table = gr.Dataframe(
            label="업데이트된 데이터"
        )

        create_btn.click(
            ui_create_quote,
            inputs=[
                create_text,
                create_author,
                create_tags,
                create_category
            ],
            outputs=[
                create_msg,
                create_table
            ]
        )

    # =====================================
    # UPDATE
    # =====================================

    with gr.Tab("4. 격언 수정"):

        update_id = gr.Number(
            label="수정할 ID",
            precision=0
        )

        update_text = gr.Textbox(
            label="새 내용"
        )

        update_author = gr.Textbox(
            label="새 작가"
        )

        update_tags = gr.Textbox(
            label="새 태그"
        )

        update_category = gr.Textbox(
            label="새 카테고리"
        )

        update_btn = gr.Button(
            "수정"
        )

        update_msg = gr.Textbox(
            label="결과"
        )

        update_table = gr.Dataframe(
            label="업데이트 데이터"
        )

        update_btn.click(
            ui_update_quote,
            inputs=[
                update_id,
                update_text,
                update_author,
                update_tags,
                update_category
            ],
            outputs=[
                update_msg,
                update_table
            ]
        )

    # =====================================
    # DELETE
    # =====================================

    with gr.Tab("5. 격언 삭제"):

        delete_id = gr.Number(
            label="삭제할 ID",
            precision=0
        )

        delete_btn = gr.Button(
            "삭제"
        )

        delete_msg = gr.Textbox(
            label="결과"
        )

        delete_table = gr.Dataframe(
            label="업데이트 데이터"
        )

        delete_btn.click(
            ui_delete_quote,
            inputs=delete_id,
            outputs=[
                delete_msg,
                delete_table
            ]
        )

    # =====================================
    # ANALYSIS
    # =====================================

    with gr.Tab("6. 분석 대시보드"):

        stats_btn = gr.Button(
            "기초 통계"
        )

        stats_table = gr.Dataframe(
            label="Summary Statistics"
        )

        word_btn = gr.Button(
            "단어 빈도 분석"
        )

        word_plot = gr.Plot()

        author_btn = gr.Button(
            "작가별 통계"
        )

        author_plot = gr.Plot()

        tag_btn = gr.Button(
            "태그별 통계"
        )

        tag_plot = gr.Plot()

        wc_btn = gr.Button(
            "워드클라우드"
        )

        wc_plot = gr.Plot()

        stats_btn.click(
            summary_stats,
            outputs=stats_table
        )

        word_btn.click(
            word_count_chart,
            outputs=word_plot
        )

        author_btn.click(
            author_chart,
            outputs=author_plot
        )

        tag_btn.click(
            tag_chart,
            outputs=tag_plot
        )

        wc_btn.click(
            wordcloud_chart,
            outputs=wc_plot
        )


# ======================================================
# MOUNT GRADIO
# ======================================================

app = gr.mount_gradio_app(
    app,
    demo,
    path="/gradio"
)