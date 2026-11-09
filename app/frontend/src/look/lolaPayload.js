// Compatible with both old servers (script only) and the structured payload API.
export function describeLolaPayload(script = "") {
  const items = [];
  const byName = new Map();
  const add = (name, qty) => {
    const dot = name.indexOf(".");
    if (dot < 1) return;
    const amount = Math.max(1, Number(qty) || 1);
    if (byName.has(name)) byName.get(name).qty += amount;
    else {
      const row = {name, swf:name.slice(0,dot), item:name.slice(dot+1), qty:amount};
      items.push(row); byName.set(name,row);
    }
  };
  for (const line of script.split(/\r?\n/)) {
    let match = line.match(/^\s*inventory\.addOptions\s+(?:"([^"\r\n]+)"|([^\s]+))\s+(\d+)/i);
    if (match) { add(match[1] || match[2],match[3]); continue; }
    match = line.match(/^\s*inventory\.add\s+(\d+)\s+"?([^"\s]+)"?/i);
    if (match) add(match[2],match[1]);
  }
  const labels = {catalog:"Catálogo", "modal.banner":"Banner", "room.change":"Portal", minigame:"Minijuego"};
  const actions = [];
  for (const match of script.matchAll(/^\s*(catalog|modal\.banner|room\.change|minigame)[ \t]+([^\r\n]+)/gm)) {
    if (!actions.some(a=>a.type===match[1] && a.target===match[2].trim())) actions.push({type:match[1],label:labels[match[1]],target:match[2].trim()});
  }
  const dialog = /:\s*SAY\b|^\s*dialog\.options\b/im.test(script);
  const kind = actions.length || dialog ? "behavior" : items.length ? "items" : "script";
  return {items, actions, kind, label:kind === "behavior" ? "Behavior / NPC" : items.length ? "Objetos preparados" : "Script de Lola", has_script:!!script.trim()};
}

export function portalDestinations(script = "") {
  const found = [];
  for (const match of script.matchAll(/^[ \t]*room\.change[ \t]+([1-9]\d*)(?:[ \t]+(\d+,\d+))?[ \t]*(?:#[^\r\n]*)?\r?$/gm)) {
    const command = `room.change ${match[1]}${match[2] ? ` ${match[2]}` : ""}`;
    if (!found.some(row => row.command === command)) found.push({room:match[1],coord:match[2] || "",command});
  }
  return found;
}

export function buildPortalPayload(script) {
  const destinations = portalDestinations(script);
  if (!destinations.length) throw new Error("Este portal no tiene un destino explícito que se pueda preparar en Lola.");
  const entry = destinations.length === 1 ? "portal0" : "choose";
  const lines = ["initial: DO", `    on activate ${entry}`, "", "INICIO: DO", `    on activate ${entry}`, ""];
  if (destinations.length > 1) {
    const choices = destinations.map(row => `Sala ${row.room}`).join("-");
    const states = destinations.map((_row,i) => `portal${i}`).join("-");
    lines.push("choose: DO", `    dialog.options "${choices}" "-" "${states}" "Elegí un destino"`, "");
  }
  destinations.forEach((row,i) => lines.push(`portal${i}: DO`, `    ${row.command}`, "    after 1 initial", ""));
  return lines.join("\r\n");
}

// Remove delivery instructions only: keep addOptions for other items and all NPC logic.
export function removePreparedItems(script, names = null) {
  const selected = names == null ? null : new Set(names);
  return script.split(/\r?\n/).filter(line => {
    const option = line.match(/^[ \t]*inventory\.addOptions[ \t]+(?:"([^"\r\n]+)"|([^\s]+))[ \t]+\d+/i);
    const plain = line.match(/^[ \t]*inventory\.add[ \t]+\d+[ \t]+"?([^"\s]+)"?/i);
    const name = option ? option[1] || option[2] : plain?.[1];
    return !name || (selected !== null && !selected.has(name));
  }).join("\r\n");
}

export function isDeliverableItem(item) {
  const name = typeof item === "string" ? item : item?.item || item?.name || "";
  return !!name && !/_so$/i.test(name);
}

export function withoutSceneDeliveries(script) {
  const excluded = describeLolaPayload(script).items.filter(item => !isDeliverableItem(item)).map(item => item.name);
  return excluded.length ? removePreparedItems(script, excluded) : script;
}
