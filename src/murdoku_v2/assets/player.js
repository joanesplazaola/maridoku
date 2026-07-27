(() => {
  const puzzle = JSON.parse(new TextDecoder().decode(
    Uint8Array.from(atob(document.querySelector("#puzzle-data").textContent), (character) => character.charCodeAt(0)),
  ));
  const cells = [...document.querySelectorAll("td[data-row]")];
  const selectors = [...document.querySelectorAll("[data-character]")];
  const status = document.querySelector(".game-status");
  const clueVersion = puzzle.cards
    .flatMap((card) => card.statements)
    .map((statement) => `${statement.id}:${statement.type}`)
    .join("|");
  const storageKey = `murdoku:${puzzle.id}:${clueVersion}`;
  const metricsKey = `${storageKey}:metrics`;
  const names = Object.fromEntries(puzzle.characters.map((character) => [character.id, character.name]));
  const characterOrder = Object.fromEntries(puzzle.characters.map((character, index) => [character.id, index]));
  const blocked = new Set(
    puzzle.board.objects
      .filter((object) => object.blocks_character)
      .flatMap((object) => object.cells.map(([row, column]) => `${row},${column}`)),
  );
  const roomAt = new Map(
    puzzle.board.rooms.flatMap((room) => room.cells.map(([row, column]) => [`${row},${column}`, room.id])),
  );
  const roomGroups = Object.fromEntries(
    (puzzle.board.room_groups || []).map((group) => [group.id, new Set(group.rooms)]),
  );
  const objectsByType = {};
  for (const object of puzzle.board.objects) {
    (objectsByType[object.type] ||= []).push(object);
  }
  let selected = puzzle.characters[0].id;
  let positions = {};
  let crosses = new Set();
  let notes = {};
  let tool = "person";
  let history = [];
  const emptyMetrics = () => ({
    sessionId: crypto.randomUUID(),
    startedAt: Date.now(),
    checks: 0,
    errors: 0,
    completedAt: null,
  });
  let metrics;
  try {
    metrics = JSON.parse(localStorage.getItem(metricsKey) || "null") || emptyMetrics();
  } catch {
    metrics = emptyMetrics();
  }
  metrics.sessionId ||= crypto.randomUUID();

  const key = (row, column) => `${row},${column}`;
  const save = () => localStorage.setItem(storageKey, JSON.stringify({
    positions,
    crosses: [...crosses],
    notes,
  }));
  const saveMetrics = () => localStorage.setItem(metricsKey, JSON.stringify(metrics));
  const snapshot = () => history.push({
    positions: structuredClone(positions),
    crosses: new Set(crosses),
    notes: structuredClone(notes),
  });

  function restore() {
    try {
      const stored = JSON.parse(localStorage.getItem(storageKey) || "{}");
      const savedPositions = stored.positions || stored;
      positions = Object.fromEntries(
        Object.entries(savedPositions).filter(([, position]) =>
          Array.isArray(position) && position.length === 2 && !blocked.has(key(...position)),
        ),
      );
      crosses = new Set((stored.crosses || []).filter((cell) => !blocked.has(cell)));
      notes = Object.fromEntries(
        Object.entries(stored.notes || {})
          .filter(([cell]) => !blocked.has(cell))
          .map(([cell, characters]) => [
            cell,
            [...new Set(characters)].filter((character) => names[character]),
          ])
          .filter(([, characters]) => characters.length),
      );
    } catch {
      positions = {};
      notes = {};
    }
  }

  function statementState(statement) {
    const args = statement.args;
    const allPlaced = Object.keys(positions).length === puzzle.characters.length;
    if (statement.type === "room_population_at_least") {
      if (!allPlaced) return null;
      return Object.values(positions).filter((position) =>
        roomAt.get(key(...position)) === args.room).length >= args.count;
    }
    const own = positions[args.character];
    if (!own) return null;
    const reference = args.reference && positions[args.reference];
    if (args.reference && !reference) return null;
    const ownRoom = roomAt.get(key(...own));
    const roomOccupants = () => Object.entries(positions)
      .filter(([, position]) => roomAt.get(key(...position)) === ownRoom);
    const objectCells = (type, occupiable = false) => (objectsByType[type] || [])
      .filter((object) => !occupiable || object.occupiable)
      .flatMap((object) => object.cells);
    if (statement.type === "victim_rule") {
      if (!allPlaced) return null;
      return roomOccupants().length === 2;
    }
    if (statement.type === "room") return ownRoom === args.room;
    if (statement.type === "exact_row") return own[0] === args.row;
    if (statement.type === "exact_column") return own[1] === args.column;
    if (statement.type === "room_population") return allPlaced ? roomOccupants().length === args.count : null;
    if (statement.type === "alone_in_room") {
      return allPlaced ? ownRoom === args.room && roomOccupants().length === 1 : null;
    }
    if (statement.type === "room_gender_count" || statement.type === "companion_gender_count") {
      if (!allPlaced) return null;
      const companions = roomOccupants().filter(([character]) =>
        statement.type === "room_gender_count" || character !== args.character,
      );
      return companions.filter(([character]) =>
        puzzle.characters.find((item) => item.id === character).gender === args.gender,
      ).length === args.count;
    }
    if (statement.type === "alone_with_gender") {
      if (!allPlaced) return null;
      const companions = roomOccupants().filter(([character]) => character !== args.character);
      return companions.length === 1
        && puzzle.characters.find((item) => item.id === companions[0][0]).gender === args.gender;
    }
    if (statement.type === "not_adjacent_to_wall" || statement.type === "in_room_corner") {
      const [row, column] = own;
      const walls = [
        row === 0 || roomAt.get(key(row - 1, column)) !== ownRoom,
        row === puzzle.board.rows - 1 || roomAt.get(key(row + 1, column)) !== ownRoom,
        column === 0 || roomAt.get(key(row, column - 1)) !== ownRoom,
        column === puzzle.board.columns - 1 || roomAt.get(key(row, column + 1)) !== ownRoom,
      ];
      return statement.type === "not_adjacent_to_wall"
        ? !walls.some(Boolean)
        : (walls[0] || walls[1]) && (walls[2] || walls[3]);
    }
    if (statement.type === "in_room_group") return roomGroups[args.group]?.has(ownRoom) || false;
    if (statement.type === "room_disjunction") return args.rooms.includes(ownRoom);
    if (statement.type === "beside_not_in_zone") {
      const zone = (puzzle.board.zones || []).find((item) => item.id === args.zone);
      if (!zone) return false;
      return !zone.cells.some(([row, column]) => row === own[0] && column === own[1])
        && zone.cells.some(([row, column]) =>
          Math.abs(own[0] - row) + Math.abs(own[1] - column) === 1);
    }
    if (statement.type === "next_to_sequence_item") {
      const sequence = (puzzle.board.sequences || []).find((item) => item.id === args.sequence);
      if (!sequence) return false;
      return [args.item - 1, args.item + 1].some((index) =>
        index >= 0 && index < sequence.cells.length
        && sequence.cells[index][0] === own[0] && sequence.cells[index][1] === own[1]);
    }
    if (statement.type === "unique_on_object") {
      if (!allPlaced) return null;
      const cells = new Set(objectCells(args.object_type, true).map((cell) => key(...cell)));
      return cells.has(key(...own))
        && Object.values(positions).filter((position) => cells.has(key(...position))).length === 1;
    }
    if (statement.type === "adjacent_object" || statement.type === "unique_adjacent_object") {
      const adjacent = ([ownRow, ownColumn]) => objectCells(args.object_type).some(([row, column]) =>
        Math.abs(ownRow - row) + Math.abs(ownColumn - column) === 1
        && roomAt.get(key(row, column)) === roomAt.get(key(ownRow, ownColumn)));
      if (statement.type === "unique_adjacent_object") {
        if (!allPlaced) return null;
        return adjacent(own)
          && Object.values(positions).filter(adjacent).length === 1;
      }
      return adjacent(own);
    }
    if (statement.type === "not_adjacent_object") {
      return !objectCells(args.object_type).some(([row, column]) =>
        Math.abs(own[0] - row) + Math.abs(own[1] - column) === 1
        && roomAt.get(key(row, column)) === ownRoom);
    }
    if (statement.type === "object_same_row_in_room") {
      return objectCells(args.object_type).some(([row, column]) =>
        row === own[0] && roomAt.get(key(row, column)) === ownRoom,
      );
    }
    if (statement.type === "object_same_column_in_room") {
      return objectCells(args.object_type).some(([row, column]) =>
        column === own[1] && roomAt.get(key(row, column)) === ownRoom,
      );
    }
    if (statement.type === "relative_row_order") {
      return args.relation === "north" ? own[0] < reference[0] : own[0] > reference[0];
    }
    if (statement.type === "relative_column_order") {
      return args.relation === "west" ? own[1] < reference[1] : own[1] > reference[1];
    }
    if (statement.type === "relative_row_distance") return own[0] - reference[0] === args.delta;
    if (statement.type === "relative_column_distance") return own[1] - reference[1] === args.delta;
    if (statement.type === "same_diagonal") {
      return Math.abs(own[0] - reference[0]) === Math.abs(own[1] - reference[1]);
    }
    if (statement.type === "same_room") return ownRoom === roomAt.get(key(...reference));
    if (statement.type === "different_room") return ownRoom !== roomAt.get(key(...reference));
    return null;
  }

  function evaluate() {
    let complete = Object.keys(positions).length === puzzle.characters.length;
    let valid = complete;
    for (const card of puzzle.cards) {
      for (const statement of card.statements) {
        const state = statementState(statement);
        valid &&= state !== false;
        complete &&= state !== null;
      }
    }
    for (const statement of puzzle.general_clues || []) {
      const state = statementState(statement);
      valid &&= state !== false;
      complete &&= state !== null;
    }
    return { complete, valid };
  }

  function render() {
    cells.forEach((cell) => {
      cell.querySelector(".character-token")?.remove();
      cell.querySelector(".candidate-notes")?.remove();
      cell.classList.toggle("crossed", crosses.has(key(Number(cell.dataset.row), Number(cell.dataset.column))));
      cell.classList.remove("duplicate-row", "duplicate-column");
    });
    for (const [cellKey, characters] of Object.entries(notes)) {
      const [row, column] = cellKey.split(",").map(Number);
      const cell = document.querySelector(`td[data-row="${row}"][data-column="${column}"]`);
      if (!cell) continue;
      const container = document.createElement("span");
      container.className = "candidate-notes";
      for (const character of [...characters].sort((a, b) => characterOrder[a] - characterOrder[b])) {
        const selector = document.querySelector(`[data-character="${character}"]`);
        const token = document.createElement("span");
        token.className = "candidate-token";
        token.style.setProperty("--portrait-x", selector.dataset.portraitX);
        token.style.setProperty("--portrait-y", selector.dataset.portraitY);
        token.title = `${names[character]} podría estar aquí`;
        token.setAttribute("aria-label", token.title);
        container.append(token);
      }
      cell.append(container);
    }
    for (const [character, [row, column]] of Object.entries(positions)) {
      const cell = document.querySelector(`td[data-row="${row}"][data-column="${column}"]`);
      const token = document.createElement("span");
      const selector = document.querySelector(`[data-character="${character}"]`);
      token.className = "character-token portrait-token";
      token.style.setProperty("--portrait-x", selector.dataset.portraitX);
      token.style.setProperty("--portrait-y", selector.dataset.portraitY);
      token.title = names[character];
      token.setAttribute("aria-label", names[character]);
      cell.append(token);
    }
    const values = Object.values(positions);
    for (const [row, column] of values) {
      const cell = document.querySelector(`td[data-row="${row}"][data-column="${column}"]`);
      cell.classList.toggle("duplicate-row", values.filter((position) => position[0] === row).length > 1);
      cell.classList.toggle("duplicate-column", values.filter((position) => position[1] === column).length > 1);
    }
    selectors.forEach((button) => button.closest(".card").classList.toggle("selected", button.dataset.character === selected));
    document.querySelectorAll("[data-tool]").forEach((button) => {
      button.classList.toggle("active", button.dataset.tool === tool);
    });
    save();
  }

  function place(cell) {
    const row = Number(cell.dataset.row);
    const column = Number(cell.dataset.column);
    const cellKey = key(row, column);
    if (blocked.has(cellKey)) {
      status.value = "Ese mueble bloquea la casilla";
      return;
    }
    if (tool === "cross") {
      if (Object.values(positions).some((position) => key(...position) === cellKey)) {
        status.value = "Borra primero el personaje";
        return;
      }
      snapshot();
      if (crosses.has(cellKey)) {
        crosses.delete(cellKey);
      } else {
        crosses.add(cellKey);
        delete notes[cellKey];
      }
      render();
      return;
    }
    if (tool === "candidate") {
      if (positions[selected]) {
        status.value = `${names[selected]} ya está colocado`;
        return;
      }
      if (Object.values(positions).some((position) => key(...position) === cellKey)) {
        status.value = "Esa casilla ya está ocupada";
        return;
      }
      snapshot();
      crosses.delete(cellKey);
      const candidates = notes[cellKey] || [];
      notes[cellKey] = candidates.includes(selected)
        ? candidates.filter((character) => character !== selected)
        : [...candidates, selected];
      if (!notes[cellKey].length) delete notes[cellKey];
      render();
      status.value = `${names[selected]}: posición posible`;
      return;
    }
    if (tool === "erase") {
      snapshot();
      crosses.delete(cellKey);
      delete notes[cellKey];
      const occupant = Object.entries(positions).find(([, position]) => position[0] === row && position[1] === column);
      if (occupant) delete positions[occupant[0]];
      render();
      return;
    }
    snapshot();
    crosses.delete(cellKey);
    if (positions[selected]?.[0] === row && positions[selected]?.[1] === column) {
      delete positions[selected];
      render();
      status.value = `${names[selected]} retirado`;
      return;
    }
    const occupant = Object.entries(positions).find(([, position]) => position[0] === row && position[1] === column);
    if (occupant && occupant[0] !== selected) delete positions[occupant[0]];
    for (const [noteCell, candidates] of Object.entries(notes)) {
      notes[noteCell] = candidates.filter((character) => character !== selected);
      if (!notes[noteCell].length || noteCell === cellKey) delete notes[noteCell];
    }
    positions[selected] = [row, column];
    render();
    status.value = `${names[selected]}: fila ${row + 1}, columna ${column + 1}`;
  }

  selectors.forEach((button) => button.addEventListener("click", () => {
    selected = button.dataset.character;
    if (tool !== "candidate") tool = "person";
    render();
    status.value = `${names[selected]} seleccionado`;
  }));
  selectors.forEach((button) => button.addEventListener("dragstart", (event) => {
    selected = button.dataset.character;
    tool = "person";
    event.dataTransfer.setData("text/plain", selected);
    event.dataTransfer.effectAllowed = "move";
    render();
  }));
  cells.forEach((cell) => {
    cell.addEventListener("click", () => place(cell));
    cell.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      const previousTool = tool;
      tool = "cross";
      place(cell);
      tool = previousTool;
      render();
    });
    cell.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
    });
    cell.addEventListener("drop", (event) => {
      event.preventDefault();
      selected = event.dataTransfer.getData("text/plain") || selected;
      place(cell);
    });
    cell.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        place(cell);
      }
    });
  });
  document.querySelector('[data-action="undo"]').addEventListener("click", () => {
    if (history.length) ({ positions, crosses, notes } = history.pop());
    render();
  });
  document.querySelector('[data-action="reset"]').addEventListener("click", () => {
    snapshot();
    positions = {};
    crosses.clear();
    notes = {};
    render();
    status.value = "Tablero reiniciado";
  });
  document.querySelectorAll("[data-tool]").forEach((button) => button.addEventListener("click", () => {
    tool = tool === button.dataset.tool ? "person" : button.dataset.tool;
    render();
  }));
  document.querySelector('[data-action="check"]').addEventListener("click", () => {
    const result = evaluate();
    metrics.checks += 1;
    if (result.complete && !result.valid) metrics.errors += 1;
    if (result.complete && result.valid && !metrics.completedAt) metrics.completedAt = Date.now();
    saveMetrics();
    status.value = result.complete && result.valid
      ? "Caso resuelto"
      : result.complete ? "La solución todavía no es correcta" : "Faltan personajes por colocar";
  });
  document.querySelector('[data-action="export"]').addEventListener("click", () => {
    const report = {
      schemaVersion: 2,
      sessionId: metrics.sessionId,
      puzzleId: puzzle.id,
      size: puzzle.board.rows,
      durationSeconds: Math.round(((metrics.completedAt || Date.now()) - metrics.startedAt) / 1000),
      checks: metrics.checks,
      errors: metrics.errors,
      completed: Boolean(metrics.completedAt),
    };
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    link.download = `${puzzle.id}-session.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    status.value = "Sesión exportada sin datos personales";
  });

  document.querySelectorAll("[data-object-type]").forEach((element) => {
    const highlight = (active) => document
      .querySelectorAll(`[data-object-type="${element.dataset.objectType}"]`)
      .forEach((match) => match.classList.toggle("object-highlight", active));
    element.addEventListener("mouseenter", () => highlight(true));
    element.addEventListener("mouseleave", () => highlight(false));
    element.addEventListener("focusin", () => highlight(true));
    element.addEventListener("focusout", () => highlight(false));
  });

  restore();
  render();
})();
