import pytest


def test_parse_raw_response_extracts_multiple_events():
    from log_parser import parse_raw_response

    payload = {
        "rawResponse": {
            "hits": {
                "hits": [
                    {
                        "_index": "lumo-logs-2026.04.25",
                        "_source": {
                            "@timestamp": "2026-04-25T10:00:00.000Z",
                            "service_name": "profile-avatars",
                            "namespace": "prod",
                            "pod_name": "p1",
                            "container_name": "c1",
                            "logmessage": "java.lang.IllegalStateException: boom\n\tat org.lumo.avatar.AvatarService.save(AvatarService.kt:12)",
                        },
                    },
                    {
                        "_index": "lumo-logs-2026.04.25",
                        "_source": {
                            "@timestamp": "2026-04-25T10:00:01.000Z",
                            "service_name": "profile-avatars",
                            "namespace": "prod",
                            "pod_name": "p2",
                            "container_name": "c1",
                            "logmessage": "kotlin.KotlinNullPointerException\n\tat org.lumo.avatar.AvatarService.load(AvatarService.kt:34)",
                        },
                    },
                ]
            }
        }
    }

    events = parse_raw_response(payload)
    assert len(events) == 2
    assert events[0].timestamp == "2026-04-25T10:00:00.000Z"
    assert events[0].service_name == "profile-avatars"
    assert events[0].raw_log.startswith("java.lang.IllegalStateException")
    assert events[1].timestamp == "2026-04-25T10:00:01.000Z"
    assert events[1].pod_name == "p2"


def test_parse_raw_response_splits_multiple_error_blocks_in_one_hit():
    from log_parser import parse_raw_response

    payload = {
        "rawResponse": {
            "hits": {
                "hits": [
                    {
                        "_index": "lumo-logs-2026.04.25",
                        "_source": {
                            "@timestamp": "2026-04-25T10:05:00.000Z",
                            "service_name": "user-center",
                            "namespace": "prod",
                            "pod_name": "p1",
                            "container_name": "c1",
                            "logmessage": "\\n".join(
                                [
                                    "10:05:00.001 [http-nio-8080-exec-7] ERROR org.hibernate.engine.jdbc.spi.SqlExceptionHelper - ORA-00001: duplicate key",
                                    "10:05:00.003 [http-nio-8080-exec-7] ERROR org.springframework.web.servlet.DispatcherServlet - Request processing failed: org.springframework.dao.DuplicateKeyException: save failed",
                                    "\tat org.springframework.web.servlet.FrameworkServlet.processRequest(FrameworkServlet.java:1)",
                                    "Caused by: org.springframework.dao.DuplicateKeyException: save failed",
                                    "\tat org.lumo.user.UserService.save(UserService.java:88)",
                                    "Caused by: java.sql.SQLIntegrityConstraintViolationException: ORA-00001: duplicate key",
                                    "\tat com.mysql.Driver.execute(Driver.java:1)",
                                    "10:05:00.400 [http-nio-8080-exec-7] WARN org.springframework.web.servlet.mvc.method.annotation.ExceptionHandlerExceptionResolver - Resolved [org.springframework.web.util.NestedServletException: Request processing failed]",
                                    "10:05:01.001 [http-nio-8080-exec-7] ERROR org.springframework.web.servlet.DispatcherServlet - Request processing failed: java.lang.IllegalStateException: second failure",
                                    "\tat org.lumo.user.UserController.create(UserController.java:21)",
                                    "Caused by: java.lang.IllegalStateException: second failure",
                                    "\tat org.lumo.user.UserService.create(UserService.java:99)",
                                ]
                            ),
                        },
                    }
                ]
            }
        }
    }

    events = parse_raw_response(payload, package_prefixes=["org.lumo."])

    assert len(events) == 2
    assert events[0].exception_type == "org.springframework.dao.DuplicateKeyException"
    assert events[0].root_cause_message == "ORA-00001: duplicate key"
    assert events[0].business_stack_frames == ["org.lumo.user.UserService.save(UserService.java:88)"]
    assert events[1].exception_type == "java.lang.IllegalStateException"
    assert events[1].root_cause_message == "second failure"
    assert events[1].business_stack_frames == [
        "org.lumo.user.UserController.create(UserController.java:21)",
        "org.lumo.user.UserService.create(UserService.java:99)",
    ]


@pytest.mark.parametrize(
    "logmessage,expected",
    [
        (
            "java.lang.IllegalStateException: boom\n\tat x.y.Z.m(Z.kt:1)",
            "java.lang.IllegalStateException",
        ),
        (
            "kotlin.KotlinNullPointerException\n\tat x.y.Z.m(Z.kt:1)",
            "kotlin.KotlinNullPointerException",
        ),
        (
            "not an exception line\n\tat x.y.Z.m(Z.kt:1)",
            None,
        ),
    ],
)
def test_extract_exception_type(logmessage, expected):
    from log_parser import extract_exception_type

    assert extract_exception_type(logmessage) == expected


def test_extract_root_cause_message_prefers_caused_by_line():
    from log_parser import extract_root_cause

    logmessage = (
        "java.lang.RuntimeException: wrapper\n"
        "\tat a.b.C.m(C.kt:1)\n"
        "Caused by: java.lang.IllegalArgumentException: bad input\n"
        "\tat org.lumo.avatar.AvatarService.save(AvatarService.kt:12)\n"
    )
    assert extract_root_cause(logmessage) == "bad input"


def test_extract_business_frames_and_first_business_frame():
    from log_parser import extract_stack_frames, extract_business_frames

    logmessage = (
        "java.lang.IllegalStateException: boom\n"
        "\tat org.springframework.web.Filter.do(Filter.java:1)\n"
        "\tat org.lumo.avatar.AvatarService.save(AvatarService.kt:12)\n"
        "\tat org.lumo.controller.MeProfileController.upload(MeProfileController.kt:87)\n"
        "\tat java.base.Thread.run(Thread.java:1)\n"
    )

    frames = extract_stack_frames(logmessage)
    business = extract_business_frames(frames, ["org.lumo."])

    assert len(frames) >= 4
    assert business == [
        "org.lumo.avatar.AvatarService.save(AvatarService.kt:12)",
        "org.lumo.controller.MeProfileController.upload(MeProfileController.kt:87)",
    ]
    assert business[0] == "org.lumo.avatar.AvatarService.save(AvatarService.kt:12)"
