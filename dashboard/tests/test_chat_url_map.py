import os
import sys

from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat.routes import chat_bp

EXPECTED = [
    ('/api/chat/conversations', ['GET'], 'chat.list_conversations'),
    ('/api/chat/conversations', ['POST'], 'chat.create_conversation'),
    ('/api/chat/conversations/<conv_id>', ['DELETE'], 'chat.delete_conversation'),
    ('/api/chat/conversations/<conv_id>', ['GET'], 'chat.get_conversation'),
    ('/api/chat/conversations/<conv_id>', ['PUT'], 'chat.update_conversation'),
    ('/api/chat/conversations/<conv_id>/cancel-active-run', ['POST'], 'chat.cancel_active_run'),
    ('/api/chat/conversations/<conv_id>/messages', ['POST'], 'chat.send_message'),
    ('/api/chat/conversations/<conv_id>/messages/<msg_id>', ['DELETE'], 'chat.delete_message'),
    ('/api/chat/conversations/<conv_id>/messages/<msg_id>', ['PUT'], 'chat.edit_message'),
    ('/api/chat/conversations/delete', ['POST'], 'chat.delete_conversations_batch'),
    ('/api/chat/ghost', ['POST'], 'chat.ghost_chat'),
    ('/api/chat/mcp-registry', ['GET'], 'chat.get_mcp_registry'),
    ('/api/chat/mcp-registry/json', ['GET'], 'chat.get_mcp_registry_json'),
    ('/api/chat/mcp-registry/json', ['PUT'], 'chat.put_mcp_registry_json'),
    ('/api/chat/mcp-registry/reload', ['POST'], 'chat.reload_mcp_registry'),
    ('/api/chat/mcp-registry/test', ['POST'], 'chat.test_mcp_registry'),
    ('/api/chat/mcp-servers', ['GET'], 'chat.get_mcp_servers'),
    ('/api/chat/messages/<msg_id>/critique', ['GET'], 'chat.get_critique'),
    ('/api/chat/messages/<msg_id>/critique', ['POST'], 'chat.create_critique'),
    ('/api/chat/projects', ['GET'], 'chat.list_projects'),
    ('/api/chat/projects', ['POST'], 'chat.create_project'),
    ('/api/chat/projects/<project_id>', ['DELETE'], 'chat.delete_project'),
    ('/api/chat/projects/<project_id>', ['GET'], 'chat.get_project'),
    ('/api/chat/projects/<project_id>', ['PUT'], 'chat.update_project'),
    ('/api/chat/projects/<project_id>/files', ['DELETE'], 'chat.project_files_delete'),
    ('/api/chat/projects/<project_id>/files', ['GET'], 'chat.project_files_tree'),
    ('/api/chat/projects/<project_id>/files/content', ['GET'], 'chat.project_files_read_content'),
    ('/api/chat/projects/<project_id>/files/content', ['PUT'], 'chat.project_files_write_content'),
    ('/api/chat/projects/<project_id>/files/copy', ['POST'], 'chat.project_files_copy'),
    ('/api/chat/projects/<project_id>/files/download', ['GET'], 'chat.project_files_download'),
    ('/api/chat/projects/<project_id>/files/mkdir', ['POST'], 'chat.project_files_mkdir'),
    ('/api/chat/projects/<project_id>/files/move', ['POST'], 'chat.project_files_move'),
    ('/api/chat/projects/<project_id>/files/upload', ['POST'], 'chat.project_files_upload'),
    ('/api/chat/prompts', ['GET'], 'chat.list_prompts'),
    ('/api/chat/prompts', ['POST'], 'chat.create_prompt'),
    ('/api/chat/prompts/<prompt_id>', ['DELETE'], 'chat.delete_prompt'),
    ('/api/chat/prompts/<prompt_id>', ['GET'], 'chat.get_prompt'),
    ('/api/chat/prompts/<prompt_id>', ['PUT'], 'chat.update_prompt'),
    ('/api/chat/prompts/reorder', ['PATCH'], 'chat.reorder_prompts'),
    ('/api/chat/providers/models', ['GET'], 'chat.list_provider_models'),
    ('/api/chat/runs/<run_id>', ['GET'], 'chat.get_run'),
    ('/api/chat/runs/<run_id>/cancel', ['POST'], 'chat.cancel_run'),
    ('/api/chat/runs/<run_id>/stream', ['GET'], 'chat.stream_run'),
    ('/api/chat/sampling-fields', ['GET'], 'chat.get_sampling_fields'),
    ('/api/chat/settings/main-system-prompt', ['DELETE'], 'chat.delete_main_system_prompt_setting'),
    ('/api/chat/settings/main-system-prompt', ['GET'], 'chat.get_main_system_prompt_setting'),
    ('/api/chat/settings/main-system-prompt', ['PUT'], 'chat.put_main_system_prompt_setting'),
    ('/api/chat/settings/openrouter-catalog', ['GET'], 'chat.get_openrouter_catalog'),
    ('/api/chat/settings/openrouter-catalog/endpoints', ['POST'], 'chat.post_openrouter_catalog_endpoints'),
    ('/api/chat/settings/openrouter-models', ['DELETE'], 'chat.delete_openrouter_models_setting'),
    ('/api/chat/settings/openrouter-models', ['GET'], 'chat.get_openrouter_models_setting'),
    ('/api/chat/settings/openrouter-models', ['PUT'], 'chat.put_openrouter_models_setting'),
    ('/api/chat/settings/openrouter-models/refresh', ['POST'], 'chat.refresh_openrouter_ladders'),
    ('/api/chat/settings/providers', ['GET'], 'chat.list_model_providers'),
    ('/api/chat/settings/providers/<provider_id>', ['DELETE'], 'chat.delete_model_provider'),
    ('/api/chat/settings/providers/<provider_id>', ['PUT'], 'chat.put_model_provider'),
    ('/api/chat/settings/providers/<provider_id>/test', ['POST'], 'chat.test_model_provider'),
    ('/api/chat/spinoff', ['POST'], 'chat.spinoff'),
]


def _actual():
    app = Flask(__name__)
    app.register_blueprint(chat_bp)
    return sorted(
        (r.rule, sorted(r.methods - {"HEAD", "OPTIONS"}), r.endpoint)
        for r in app.url_map.iter_rules()
        if r.endpoint.startswith("chat.")
    )


def test_the_chat_blueprint_serves_exactly_the_recorded_routes():
    assert _actual() == EXPECTED

