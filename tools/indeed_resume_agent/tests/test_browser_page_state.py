from tools.indeed_resume_agent.browser_page_state import (
    is_generic_recruiting_landing,
    requires_human,
    url_requires_human,
)


class FakeLocator:
    def __init__(self, *, count=0, text=""):
        self._count = count
        self._text = text

    def count(self):
        return self._count

    def inner_text(self, timeout=None):
        return self._text


class FakeFrame:
    def __init__(self, url):
        self.url = url


class FakePage:
    def __init__(
        self,
        *,
        url="https://employers.indeed.com/candidates",
        frames=None,
        challenge_count=0,
        body_text="",
    ):
        self.url = url
        self.frames = list(frames or [])
        self.challenge_count = challenge_count
        self.body_text = body_text

    def locator(self, selector):
        if selector == "body":
            return FakeLocator(text=self.body_text)
        return FakeLocator(count=self.challenge_count)


def test_url_requires_human_detects_auth_and_challenge_urls():
    assert url_requires_human("https://employers.indeed.com/login") is True
    assert url_requires_human("https://example.test/CAPTCHA/start") is True
    assert url_requires_human("https://employers.indeed.com/candidates") is False


def test_requires_human_detects_top_level_challenge_url():
    page = FakePage(url="https://employers.indeed.com/signin")

    assert requires_human(page) is True


def test_requires_human_detects_challenge_iframe():
    page = FakePage(
        frames=[FakeFrame("https://security.example/challenge/abc")]
    )

    assert requires_human(page) is True


def test_requires_human_detects_challenge_nodes():
    page = FakePage(challenge_count=1)

    assert requires_human(page) is True


def test_requires_human_detects_body_markers_and_allows_normal_page():
    challenge_page = FakePage(body_text="Please complete this security challenge")
    normal_page = FakePage(body_text="Candidates ready for review")

    assert requires_human(challenge_page) is True
    assert requires_human(normal_page) is False


def test_generic_recruiting_landing_requires_resumes_root():
    assert (
        is_generic_recruiting_landing(
            FakePage(url="https://resumes.indeed.com/")
        )
        is True
    )
    assert (
        is_generic_recruiting_landing(
            FakePage(url="https://resumes.indeed.com/candidate/123")
        )
        is False
    )
    assert (
        is_generic_recruiting_landing(
            FakePage(url="https://employers.indeed.com/")
        )
        is False
    )
