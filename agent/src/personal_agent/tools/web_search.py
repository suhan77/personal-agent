"""읽기 전용 웹 검색 도구를 구성한다."""

from langchain_community.tools import DuckDuckGoSearchResults


def create_web_search_tool() -> DuckDuckGoSearchResults:
    """검색 결과의 제목, 요약, URL을 최대 네 건 반환한다."""
    return DuckDuckGoSearchResults(
        name="web_search",
        description="최신 정보나 웹 페이지·블로그 글을 검색한다. query에 구체적인 검색어를 입력한다. 검색 결과에 없는 내용을 확인한 사실처럼 말하지 말고, 사용한 결과의 URL을 답변에 포함한다.",
        num_results=4,
        output_format="json",
    )
