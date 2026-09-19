import pytest
from fastapi.testclient import TestClient

from reels_api.auth import SESSION_COOKIE, session_cookie_value, unasked_cookie_value
from reels_api.main import create_app
from reels_api.models import Job, JobStatus, Source
from reels_api.web import AttemptLimiter
from tests.conftest import make_settings
from tests.test_routes import FakePipeline, _done_reel

PASSCODE = "letmein"
INVITE = "invite-token-0123456789"
APP_MODULES = ["app.js", "api.js", "format.js", "icons.js", "board.js", "paste.js", "toast.js", "player.js", "watch.js", "cookie.js"]
FONT_FILES = ["bricolage-grotesque-latin.woff2", "bricolage-grotesque-latin-ext.woff2"]
GOOGLE_FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")
NOTICE_LINES = (
    "one cookie keeps this phone logged in for a year.",
    "nothing else is stored. no tracking, no ads.",
    "you can log out from the board any time.",
)


@pytest.fixture
def web_app(tmp_path):
    def factory(**overrides):
        settings = make_settings(tmp_path, web_passcode=PASSCODE, **overrides)
        return create_app(settings=settings, pipeline=FakePipeline(settings))
    return factory


def https_client(app) -> TestClient:
    # The cookie is Secure; httpx only sends it back over https.
    return TestClient(app, base_url="https://testserver")


def set_unasked_cookie(client) -> None:
    # A cookie set before the login page asked (pop-up spec 3).
    client.cookies.set(SESSION_COOKIE, unasked_cookie_value(client.app.state.settings))


# ---- AttemptLimiter

class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_limiter_blocks_after_max_failures_and_expires():
    clock = FakeClock()
    limiter = AttemptLimiter(max_attempts=3, window_seconds=900, clock=clock)
    assert limiter.is_blocked("1.1.1.1") is False
    for _ in range(3):
        limiter.record_failure("1.1.1.1")
    assert limiter.is_blocked("1.1.1.1") is True
    assert limiter.is_blocked("2.2.2.2") is False

    clock.now += 901
    assert limiter.is_blocked("1.1.1.1") is False


def test_limiter_clear_and_prunes_other_ips():
    clock = FakeClock()
    limiter = AttemptLimiter(max_attempts=2, window_seconds=60, clock=clock)
    limiter.record_failure("a")
    limiter.record_failure("b")
    limiter.record_failure("b")
    assert limiter.is_blocked("b") is True
    limiter.clear("b")
    assert limiter.is_blocked("b") is False

    clock.now += 61
    limiter.is_blocked("zzz")          # any call prunes every entry
    assert limiter._attempts == {}


# ---- POST /web/login

def test_login_success_sets_cookie(web_app):
    with https_client(web_app()) as client:
        r = client.post("/web/login", json={"passcode": PASSCODE})
        assert r.status_code == 204
        assert r.content == b""
        cookie = r.headers["set-cookie"]
        assert unasked_cookie_value(client.app.state.settings) not in cookie
        assert cookie.startswith(f"{SESSION_COOKIE}={session_cookie_value(client.app.state.settings)};")
        lowered = cookie.lower()
        for attr in ("httponly", "secure", "samesite=lax", "path=/", "max-age=31536000"):
            assert attr in lowered, attr


def test_login_wrong_passcode(web_app):
    with https_client(web_app()) as client:
        r = client.post("/web/login", json={"passcode": "nope"})
        assert r.status_code == 401
        assert r.json() == {"error": "wrong_passcode", "message": "That passcode is not right."}
        assert "set-cookie" not in r.headers


def test_login_malformed_body_422(web_app):
    with https_client(web_app()) as client:
        assert client.post("/web/login", json={}).status_code == 422


def test_login_rate_limited_after_ten_failures(web_app):
    with https_client(web_app()) as client:
        for _ in range(10):
            assert client.post("/web/login", json={"passcode": "nope"}).status_code == 401
        r = client.post("/web/login", json={"passcode": PASSCODE})   # right passcode, still blocked
        assert r.status_code == 429
        assert r.json() == {
            "error": "too_many_attempts",
            "message": "Too many wrong tries. Wait 15 minutes and try again.",
        }


def test_login_success_clears_counter(web_app):
    with https_client(web_app()) as client:
        for _ in range(9):
            client.post("/web/login", json={"passcode": "nope"})
        assert client.post("/web/login", json={"passcode": PASSCODE}).status_code == 204
        for _ in range(9):
            assert client.post("/web/login", json={"passcode": "nope"}).status_code == 401


# ---- POST /web/logout (cookie spec 5.3)

def test_logout_deletes_the_cookie(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        r = client.post("/web/logout")
        assert r.status_code == 204
        cookie = r.headers["set-cookie"]
        assert cookie.startswith(f'{SESSION_COOKIE}="";')
        lowered = cookie.lower()
        for attr in ("httponly", "secure", "samesite=lax", "path=/", "max-age=0"):
            assert attr in lowered, attr
        assert _is_login(client.get("/"))
        assert client.get("/jobs").status_code == 401


def test_logout_without_cookie_is_401(web_app):
    with https_client(web_app()) as client:
        r = client.post("/web/logout")
        assert r.status_code == 401
        assert r.json() == {"error": "unauthorized", "message": "Missing or invalid API key."}
        assert "set-cookie" not in r.headers


def test_logout_deletes_an_unasked_cookie(web_app):
    with https_client(web_app()) as client:
        set_unasked_cookie(client)
        r = client.post("/web/logout")
        assert r.status_code == 204
        assert r.headers["set-cookie"].startswith(f'{SESSION_COOKIE}="";')


# ---- POST /web/cookie: allow cookie on the board's pop-up (pop-up spec 5.2)

def test_agree_to_cookie_marks_an_unasked_cookie_as_agreed(web_app):
    with https_client(web_app()) as client:
        settings = client.app.state.settings
        set_unasked_cookie(client)
        r = client.post("/web/cookie")
        assert r.status_code == 204
        assert r.content == b""
        assert r.headers["cache-control"] == "no-store"
        cookie = r.headers["set-cookie"]
        assert cookie.startswith(f"{SESSION_COOKIE}={session_cookie_value(settings)};")
        lowered = cookie.lower()
        for attr in ("httponly", "secure", "samesite=lax", "path=/", "max-age=31536000"):
            assert attr in lowered, attr

        # The jar would now hold two cookies (the hand-set one and the response's); keep only the new one.
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, cookie.split(";")[0].split("=", 1)[1])
        assert '<body data-cookie="agreed">' in client.get("/").text


def test_agree_to_cookie_with_agreed_cookie(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        r = client.post("/web/cookie")
        assert r.status_code == 204
        assert r.headers["set-cookie"].startswith(f"{SESSION_COOKIE}={session_cookie_value(client.app.state.settings)};")


def test_agree_to_cookie_needs_the_cookie(web_app):
    with https_client(web_app()) as client:
        for cookie in (None, "garbage"):
            client.cookies.clear()
            if cookie:
                client.cookies.set(SESSION_COOKIE, cookie)
            for headers in ({}, {"X-API-Key": "test-key"}):  # an API key alone has no cookie to mark
                r = client.post("/web/cookie", headers=headers)
                assert r.status_code == 401, (cookie, headers)
                assert r.json() == {"error": "unauthorized", "message": "Missing or invalid API key."}
                assert "set-cookie" not in r.headers
                assert r.headers["cache-control"] == "no-store"


def test_board_has_log_out(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        page = client.get("/").text
    assert '<footer class="board-foot">' in page
    assert "one cookie keeps you logged in" in page
    assert 'id="logout"' in page


def test_board_has_the_cookie_pop_up(web_app):
    with https_client(web_app()) as client:
        set_unasked_cookie(client)
        page = client.get("/").text
    assert '<dialog id="cookie-ask" class="cookie-ask" aria-labelledby="cookie-ask-title">' in page
    assert "this site uses one cookie" in page
    for line in NOTICE_LINES:
        assert line in page, line
    assert ">allow cookie</button>" in page
    assert "no thanks, log me out" in page
    for element_id in ("cookie-ask-title", "cookie-allow", "cookie-error", "cookie-decline"):
        assert f'id="{element_id}"' in page, element_id


# ---- GET / and the cookie round-trip

def test_index_serves_login_then_app(web_app):
    with https_client(web_app()) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert r.headers["cache-control"] == "no-store"
        assert 'id="passcode"' in r.text

        client.post("/web/login", json={"passcode": PASSCODE})
        r = client.get("/?text=hello")
        assert r.status_code == 200
        assert 'id="grid"' in r.text
        assert r.headers["cache-control"] == "no-store"

        # the same cookie now unlocks the API
        assert client.get("/jobs").status_code == 200


def test_index_ignores_bad_cookie(web_app):
    with https_client(web_app()) as client:
        client.cookies.set(SESSION_COOKIE, "garbage")
        r = client.get("/")
        assert 'id="passcode"' in r.text


def test_login_page_asks_before_the_cookie(web_app):
    with TestClient(web_app()) as client:
        page = client.get("/").text
    for line in NOTICE_LINES:
        assert line in page, line
    assert "allow cookie &amp; log in" in page
    assert "no thanks" in page
    assert "no cookie, no login" in page
    assert "changed my mind" in page
    for element_id in ("ask", "declined", "login-lead", "decline", "reconsider"):
        assert f'id="{element_id}"' in page, element_id
    assert "autofocus" not in page


# ---- manifest, service worker, static files

def test_manifest_sw_and_static(web_app):
    with TestClient(web_app()) as client:
        m = client.get("/manifest.webmanifest")
        assert m.status_code == 200
        assert m.headers["content-type"].startswith("application/manifest+json")
        assert m.headers["cache-control"] == "no-cache"
        assert m.json()["share_target"]["action"] == "/"
        assert m.json()["theme_color"] == "#0a0b0d"

        sw = client.get("/sw.js")
        assert sw.status_code == 200
        assert sw.headers["content-type"].startswith("text/javascript")
        assert sw.headers["cache-control"] == "no-cache"

        icon = client.get("/static/icon-192.png")
        assert icon.status_code == 200
        assert icon.headers["content-type"] == "image/png"
        assert icon.headers["cache-control"] == "no-cache"

        assert client.get("/static/missing.js").status_code == 404


# ---- disabled mode

@pytest.mark.parametrize("passcode", [None, ""])
def test_web_disabled_when_passcode_unset(tmp_path, passcode):
    settings = make_settings(tmp_path, web_passcode=passcode)
    app = create_app(settings=settings, pipeline=FakePipeline(settings))
    with TestClient(app) as client:
        for path in ("/", "/manifest.webmanifest", "/sw.js", "/static/icon-192.png"):
            assert client.get(path).status_code == 404, path
        assert client.post("/web/login", json={"passcode": "x"}).status_code == 404
        assert client.post("/web/logout").status_code == 404
        assert client.post("/web/cookie").status_code == 404
        assert client.get("/health").status_code == 200


def test_page_assets_are_served(web_app):
    with TestClient(web_app()) as client:
        for path, prefix in (("/static/style.css", "text/css"), ("/static/login.js", "text/javascript")):
            r = client.get(path)
            assert r.status_code == 200, path
            assert r.headers["content-type"].startswith(prefix), path
            assert r.headers["cache-control"] == "no-cache"


def test_app_modules_are_served(web_app):
    with TestClient(web_app()) as client:
        for name in APP_MODULES:
            r = client.get(f"/static/{name}")
            assert r.status_code == 200, name
            assert r.headers["content-type"].startswith("text/javascript"), name
            assert r.headers["cache-control"] == "no-cache", name


def test_font_files_are_served(web_app):
    with TestClient(web_app()) as client:
        for name in FONT_FILES:
            r = client.get(f"/static/fonts/{name}")
            assert r.status_code == 200, name
            assert r.headers["content-type"] == "font/woff2", name
            assert r.headers["cache-control"] == "no-cache", name
            assert r.content[:4] == b"wOF2", name
        license_text = client.get("/static/fonts/OFL.txt")
        assert license_text.status_code == 200
        assert "SIL OPEN FONT LICENSE" in license_text.text.upper()
        css = client.get("/static/style.css").text
    for name in FONT_FILES:
        assert f'url("/static/fonts/{name}") format("woff2")' in css, name


def test_no_page_loads_google_fonts(web_app):
    with https_client(web_app()) as client:
        reel = _done_reel(client)
        pages = {
            "login": client.get("/").text,
            "view-only": client.get("/", params={"reel": reel["id"], "k": reel["share_key"]}).text,
            "expired": client.get("/", params={"reel": "nope", "k": "x"}).text,
        }
        client.post("/web/login", json={"passcode": PASSCODE})
        pages["board"] = client.get("/").text
    assert 'id="reel-data"' in pages["view-only"]
    assert "this reel has expired" in pages["expired"]
    assert 'id="grid"' in pages["board"]
    for name, page in pages.items():
        for host in GOOGLE_FONT_HOSTS:
            assert host not in page, (name, host)


def test_app_page_loads_entry_module(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        html = client.get("/").text
    assert '<script type="module" src="/static/app.js"></script>' in html


# ---- GET /join/{token}: asks first, never sets the cookie (cookie spec 5.1)

def test_join_with_right_token_shows_invite_page_without_cookie(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        r = client.get(f"/join/{INVITE}", follow_redirects=False)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert r.headers["cache-control"] == "no-store"
        assert 'id="login-form"' in r.text
        assert "set-cookie" not in r.headers
        assert client.get("/jobs").status_code == 401


def test_join_with_cookie_goes_to_board_without_counting(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        for _ in range(10):
            r = client.get("/join/wrong", follow_redirects=False)
            assert r.status_code == 303
            assert r.headers["location"] == "/"
            assert r.headers["cache-control"] == "no-store"
        client.cookies.clear()
        assert client.post("/web/login", json={"passcode": PASSCODE}).status_code == 204   # not blocked


def test_join_with_unasked_cookie_goes_to_board_without_counting(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        set_unasked_cookie(client)
        for _ in range(10):
            r = client.get("/join/wrong", follow_redirects=False)
            assert r.status_code == 303
            assert r.headers["location"] == "/"
            assert "set-cookie" not in r.headers
        client.cookies.clear()
        assert client.post("/web/login", json={"passcode": PASSCODE}).status_code == 204   # not blocked


def test_join_with_wrong_token_redirects_without_cookie(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        r = client.get("/join/wrong-token-0123456789", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        assert r.headers["cache-control"] == "no-store"
        assert "set-cookie" not in r.headers
        assert client.get("/jobs").status_code == 401


def test_join_blocked_after_ten_wrong_tokens(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        for _ in range(10):
            client.get("/join/wrong", follow_redirects=False)
        r = client.get(f"/join/{INVITE}", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        assert "set-cookie" not in r.headers


def test_join_page_does_not_clear_counter(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        for _ in range(9):
            client.post("/join/wrong")
        assert client.get(f"/join/{INVITE}", follow_redirects=False).status_code == 200
        client.post("/join/wrong")
        assert client.post(f"/join/{INVITE}").status_code == 429


# ---- POST /join/{token}: allow cookie & join (cookie spec 5.2)

def test_accept_invite_with_right_token_sets_cookie(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        r = client.post(f"/join/{INVITE}")
        assert r.status_code == 204
        assert r.content == b""
        assert r.headers["cache-control"] == "no-store"
        cookie = r.headers["set-cookie"]
        assert unasked_cookie_value(client.app.state.settings) not in cookie
        assert cookie.startswith(f"{SESSION_COOKIE}={session_cookie_value(client.app.state.settings)};")
        lowered = cookie.lower()
        for attr in ("httponly", "secure", "samesite=lax", "path=/", "max-age=31536000"):
            assert attr in lowered, attr
        assert client.get("/jobs").status_code == 200


def test_accept_invite_with_wrong_token(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        r = client.post("/join/wrong-token-0123456789")
        assert r.status_code == 401
        assert r.json() == {"error": "invalid_invite", "message": "That invite link is not right."}
        assert r.headers["cache-control"] == "no-store"
        assert "set-cookie" not in r.headers


def test_accept_invite_blocked_after_ten_wrong_tokens(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        for _ in range(10):
            assert client.post("/join/wrong").status_code == 401
        r = client.post(f"/join/{INVITE}")                   # right token, still blocked
        assert r.status_code == 429
        assert r.json() == {
            "error": "too_many_attempts",
            "message": "Too many wrong tries. Wait 15 minutes and try again.",
        }
        assert r.headers["cache-control"] == "no-store"
        assert "set-cookie" not in r.headers


def test_accept_invite_clears_counter(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        for _ in range(9):
            client.post("/join/wrong")
        assert client.post(f"/join/{INVITE}").status_code == 204
        client.cookies.clear()
        for _ in range(9):
            assert client.post("/join/wrong").status_code == 401


def test_wrong_passcodes_and_wrong_tokens_share_one_limit(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        for _ in range(3):
            client.post("/web/login", json={"passcode": "nope"})
            client.get("/join/wrong", follow_redirects=False)
            client.post("/join/wrong")
        client.post("/web/login", json={"passcode": "nope"})                          # tenth failure
        assert client.get(f"/join/{INVITE}", follow_redirects=False).status_code == 303
        assert client.post("/web/login", json={"passcode": PASSCODE}).status_code == 429


def test_join_404_without_invite_token(web_app):
    with TestClient(web_app()) as client:
        assert client.get(f"/join/{INVITE}", follow_redirects=False).status_code == 404
        assert client.post(f"/join/{INVITE}").status_code == 404


def test_join_404_when_web_disabled(tmp_path):
    settings = make_settings(tmp_path, invite_token=INVITE)
    app = create_app(settings=settings, pipeline=FakePipeline(settings))
    with TestClient(app) as client:
        assert client.get(f"/join/{INVITE}", follow_redirects=False).status_code == 404
        assert client.post(f"/join/{INVITE}").status_code == 404


# ---- GET / with a share link (links spec 5.1)

def _is_login(r):
    return r.status_code == 200 and 'id="passcode"' in r.text and r.headers["cache-control"] == "no-store"


def _is_expired(r):
    return r.status_code == 200 and "this reel has expired" in r.text and r.headers["cache-control"] == "no-store"


def test_index_with_cookie_ignores_share_key(web_app):
    with https_client(web_app()) as client:
        reel = _done_reel(client)
        client.post("/web/login", json={"passcode": PASSCODE})
        r = client.get("/", params={"reel": reel["id"], "k": reel["share_key"]})
        assert 'id="grid"' in r.text
        assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "params",
    [{"reel": "abc"}, {"k": "abc"}, {"reel": "abc", "k": ""}, {"reel": "", "k": "abc"}],
)
def test_index_without_reel_and_key_is_login(web_app, params):
    with TestClient(web_app()) as client:
        assert _is_login(client.get("/", params=params))


def test_index_unknown_reel_is_expired(web_app):
    with TestClient(web_app(retention_hours=12)) as client:
        r = client.get("/", params={"reel": "nope", "k": "whatever"})
        assert _is_expired(r)
        assert r.headers["content-type"].startswith("text/html")
        assert "reels only stay up for 12 hours" in r.text
    with TestClient(web_app(retention_hours=1)) as client:
        assert "reels only stay up for 1 hour<" in client.get("/", params={"reel": "nope", "k": "x"}).text


def test_index_wrong_key_is_login(web_app):
    with TestClient(web_app()) as client:
        reel = _done_reel(client)
        assert _is_login(client.get("/", params={"reel": reel["id"], "k": "wrong-key-000000"}))


def test_index_failed_job_or_missing_file_is_expired(web_app):
    with TestClient(web_app()) as client:
        failed = Job(id="failed1", url="u", source=Source.TIKTOK, status=JobStatus.FAILED)
        client.app.state.store._jobs[failed.id] = failed
        assert _is_expired(client.get("/", params={"reel": failed.id, "k": failed.share_key}))

        reel = _done_reel(client)
        client.app.state.store._jobs[reel["id"]].result.file_path.unlink()
        assert _is_expired(client.get("/", params={"reel": reel["id"], "k": reel["share_key"]}))


def test_index_right_key_is_view_only_page(web_app):
    with TestClient(web_app()) as client:
        reel = _done_reel(client)
        key = reel["share_key"]
        r = client.get("/", params={"reel": reel["id"], "k": key})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert r.headers["cache-control"] == "no-store"
        assert '<script type="module" src="/static/watch.js"></script>' in r.text
        assert f'"file_url": "/files/{reel["id"]}.mp4?k={key}"' in r.text
        assert f'content="http://testserver/?reel={reel["id"]}&amp;k={key}"' in r.text
        assert f'content="http://testserver/files/{reel["id"]}.jpg?k={key}"' in r.text
        # the page's own file links work without a cookie
        assert client.get(f"/files/{reel['id']}.mp4", params={"k": key}).status_code == 200


def test_view_only_page_uses_public_base_url(web_app):
    with TestClient(web_app(public_base_url="https://reels.example.com/")) as client:
        reel = _done_reel(client)
        r = client.get("/", params={"reel": reel["id"], "k": reel["share_key"]})
        assert f'content="https://reels.example.com/files/{reel["id"]}.jpg?k={reel["share_key"]}"' in r.text


def test_login_and_app_pages_have_preview_tags(web_app):
    with https_client(web_app()) as client:
        login = client.get("/").text
        client.post("/web/login", json={"passcode": PASSCODE})
        board = client.get("/").text
    for page in (login, board):
        assert '<meta name="robots" content="noindex">' in page
        assert '<meta property="og:title" content="reels">' in page
        assert '<meta property="og:description" content="reels your friends pasted. no names, ever.">' in page
        assert '<meta property="og:type" content="website">' in page
        assert '<meta property="og:site_name" content="reels">' in page


# ---- GET / with a cookie set before the login page asked (pop-up spec 4)

def _is_ask_board(r):
    return (
        r.status_code == 200
        and r.headers["content-type"].startswith("text/html")
        and r.headers["cache-control"] == "no-store"
        and 'id="grid"' in r.text
        and '<body data-cookie="ask">' in r.text
    )


@pytest.mark.parametrize(
    "params",
    [{}, {"url": "https://vm.tiktok.com/x/", "text": "look"}, {"reel": "abc"}, {"reel": "abc", "k": ""}],
)
def test_index_with_unasked_cookie_asks_on_the_board(web_app, params):
    with https_client(web_app()) as client:
        set_unasked_cookie(client)
        assert _is_ask_board(client.get("/", params=params))


def test_index_with_agreed_cookie_does_not_ask(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        r = client.get("/")
        assert 'id="grid"' in r.text
        assert '<body data-cookie="agreed">' in r.text


def test_index_with_unasked_cookie_treats_share_links_as_without_cookie(web_app):
    with https_client(web_app()) as client:
        reel = _done_reel(client)
        failed = Job(id="failed1", url="u", source=Source.TIKTOK, status=JobStatus.FAILED)
        client.app.state.store._jobs[failed.id] = failed
        set_unasked_cookie(client)

        r = client.get("/", params={"reel": reel["id"], "k": reel["share_key"]})
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-store"
        assert '<script type="module" src="/static/watch.js"></script>' in r.text
        assert "data-cookie" not in r.text

        assert _is_ask_board(client.get("/", params={"reel": reel["id"], "k": "wrong-key-000000"}))
        assert _is_expired(client.get("/", params={"reel": "nope", "k": "whatever"}))
        assert _is_expired(client.get("/", params={"reel": failed.id, "k": failed.share_key}))
