// preview.swf changeAttr toggles the character visibility on EVERY call.
// Keep that legacy toggle behind an idempotent API, scoped to each player.
const wornPlayers = new WeakSet();

export function showPreviewObject(player, asset) {
  player.previewAsset(asset);
  wornPlayers.delete(player); // previewAsset resets the SWF toggle to false.
}

export function showPreviewLook(player, json) {
  if (wornPlayers.has(player)) {
    player.changeAttr(json); // toggle off before applying the next look
    wornPlayers.delete(player);
  }
  player.changeAttr(json); // toggle on and apply attributes
  wornPlayers.add(player);
}
