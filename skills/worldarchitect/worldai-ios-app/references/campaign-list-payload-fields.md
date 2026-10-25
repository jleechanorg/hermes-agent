# Campaign-list payload: why a field the app expects is missing

Symptom: the campaign list (any client — iOS `CampaignsScreen`, the web dashboard, a new
integration) renders rows without a field the Firestore document actually has — portraits,
theme, status. The campaign detail screen shows the value fine.

## The choke point

`GET /api/campaigns` -> `mvp_site/main.py:get_campaigns` -> MCP tool `get_campaigns_list` ->
`world_logic.get_campaigns_list_unified()` -> `firestore_service.get_campaigns_for_user()`.

That last function builds the list with a **field-mask projection**, not a full document read:

```python
campaigns_query = campaigns_ref.select(
    ["title", "created_at", "last_played", "initial_prompt", "prompt"]
)
```

`select()` is a Firestore field mask: **anything not listed is absent from the response**, so a
field can be present on the document (and returned by the per-campaign `GET /api/campaigns/<id>`)
and still be invisible to every list client. `avatar_url` was exactly this case — portrait uploads
worked, the detail header showed the art, and the list payload never carried it.

## Fix shape (additive, list-view only)

1. Add the field to that projection (`"avatar_url"`), keeping every existing entry.
2. Update the projection test — `mvp_site/tests/test_campaign_pagination.py::
   test_campaign_list_selects_minimal_fields` asserts the exact list with
   `mock_collection.select.assert_called_once_with([...])`, so an un-updated test fails loudly
   (that is the intended tripwire, not a nuisance).
3. Prove the field survives the whole chain, not just the projection: call
   `world_logic.get_campaigns_list_unified({...})` with a mocked document whose `to_dict()` honours
   the field mask and assert the returned campaign dict carries the key.
4. Run it against real Firestore from the PR worktree before trusting the client:
   `python3 -c "from mvp_site import firestore_service; ..."` with `bash -lic` (service-account creds
   come from `~/.bashrc`) — print field presence per campaign, never whole URLs.

## Client side

- iOS maps the payload in `src/services/mvpSiteClient.ts::mapMvpCampaign` (`MvpCampaign` interface ->
  `Campaign` = `WorldListItem`); a wire field that the interface does not declare is silently dropped
  by the mapper even when the server sends it. Add the snake_case wire field, map it to the camelCase
  model field, and normalise `''`/whitespace to `null`.
- The list API is a **dependency**: shipping the client change alone renders exactly the old UI, so
  say so in the PR and link the backend PR.

## Debug order that avoids a wasted client investigation

1. `curl` the list endpoint (with a token) and check whether the field is in the JSON at all.
2. If absent: read the projection list above — it is almost always the answer.
3. If present: the client mapper or the component is dropping it.
