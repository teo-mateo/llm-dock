from dataclasses import replace

from flask import current_app

from .deps import ChatDeps

DEPS_KEY = "CHAT_DEPS"


def deps_for(app) -> ChatDeps:
    return app.config[DEPS_KEY]


def deps() -> ChatDeps:
    return deps_for(current_app)


def install(app, **parts) -> ChatDeps:
    chat_deps = ChatDeps(**parts)
    app.config[DEPS_KEY] = chat_deps
    return chat_deps


def replace_deps(app, **parts) -> ChatDeps:
    chat_deps = replace(deps_for(app), **parts)
    app.config[DEPS_KEY] = chat_deps
    return chat_deps
