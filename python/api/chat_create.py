from python.helpers.api import ApiHandler, Input, Output, Request, Response


from python.helpers import guids, persist_chat
from agent import AgentContext


class CreateChat(ApiHandler):
    def _is_context_id_taken(self, ctxid: str) -> bool:
        if not ctxid:
            return True
        if AgentContext.get(ctxid):
            return True
        # Also avoid ids that already exist on disk but are not loaded yet.
        chat_path = persist_chat.get_chat_folder_path(ctxid)
        from python.helpers import files

        return files.exists(chat_path)

    def _resolve_new_context_id(self, preferred: str | None = None) -> str:
        candidate = str(preferred or "").strip()
        if candidate and not self._is_context_id_taken(candidate):
            return candidate
        while True:
            candidate = guids.generate_id()
            if not self._is_context_id_taken(candidate):
                return candidate

    async def process(self, input: Input, request: Request) -> Output:
        current_ctxid = input.get("current_context", "")  # current context id
        requested_new_ctxid = input.get("new_context", "")  # optional preferred id

        # context instance - get or create
        current_context = AgentContext.get(current_ctxid)

        # Resolve a guaranteed-fresh context id.
        new_ctxid = self._resolve_new_context_id(requested_new_ctxid)

        # get/create new context
        new_context = self.use_context(new_ctxid)

        # copy selected data from current to new context
        # do not create new chats in the same project anymore, it can be annoying
        # if current_context:
            # current_data_1 = current_context.get_data(projects.CONTEXT_DATA_KEY_PROJECT)
            # if current_data_1:
            #     new_context.set_data(projects.CONTEXT_DATA_KEY_PROJECT, current_data_1)
            # current_data_2 = current_context.get_output_data(projects.CONTEXT_DATA_KEY_PROJECT)
            # if current_data_2:
            #     new_context.set_output_data(projects.CONTEXT_DATA_KEY_PROJECT, current_data_2)

        # New context should appear in other tabs' chat lists via state_push.
        from python.helpers.state_monitor_integration import mark_dirty_all
        mark_dirty_all(reason="api.chat_create.CreateChat")

        return {
            "ok": True,
            "ctxid": new_context.id,
            "message": "Context created.",
        }
