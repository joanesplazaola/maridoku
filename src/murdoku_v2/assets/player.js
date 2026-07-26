(() => {
  const puzzle = JSON.parse(new TextDecoder().decode(
    Uint8Array.from(atob(document.querySelector("#puzzle-data").textContent), (character) => character.charCodeAt(0)),
  ));
  const cells = [...document.querySelectorAll("td[data-row]")];
  const selectors = [...document.querySelectorAll("[data-character]")];
  const status = document.querySelector(".game-status");
  const storageKey = `murdoku:${puzzle.id}`;
  const metricsKey = `${storageKey}:metrics`;
  const names = Object.fromEntries(puzzle.characters.map((character) => [character.id, character.name]));
  const blocked = new Set(
    puzzle.board.objects
      .filter((object) => object.blocks_character)
      .flatMap((object) => object.cells.map(([row, column]) => `${row},${column}`)),
  );
  const roomAt = new Map(
    puzzle.board.rooms.flatMap((room) => room.cells.map(([row, column]) => [`${row},${column}`, room.id])),
  );
  let selected = puzzle.characters[0].id;
  let positions = {};
  let history = [];
  const emptyMetrics = () => ({
    startedAt: Date.now(),
    checks: 0,
    errors: 0,
    hints: 0,
    completedAt: null,
  });
  let metrics;
  try {
    metrics = JSON.parse(localStorage.getItem(metricsKey) || "null") || emptyMetrics();
  } catch {
    metrics = emptyMetrics();
  }

  const key = (row, column) => `${row},${column}`;
  const save = () => localStorage.setItem(storageKey, JSON.stringify(positions));
  const saveMetrics = () => localStorage.setItem(metricsKey, JSON.stringify(metrics));
  const snapshot = () => history.push(structuredClone(positions));

  function restore() {
    try {
      const stored = JSON.parse(localStorage.getItem(storageKey) || "{}");
      positions = Object.fromEntries(
        Object.entries(stored).filter(([, position]) =>
          Array.isArray(position) && position.length === 2 && !blocked.has(key(...position)),
        ),
      );
    } catch {
      positions = {};
    }
  }

  function statementState(statement) {
    const args = statement.args;
    const own = positions[args.character];
    if (!own) return null;
    const reference = args.reference && positions[args.reference];
    if (args.reference && !reference) return null;
    if (statement.type === "victim_rule") {
      if (Object.keys(positions).length !== puzzle.characters.length) return null;
      const room = roomAt.get(key(...own));
      return Object.values(positions).filter((position) => roomAt.get(key(...position)) === room).length === 2;
    }
    if (statement.type === "exact_row") return own[0] === args.row;
    if (statement.type === "exact_column") return own[1] === args.column;
    if (statement.type === "relative_row_order") {
      return args.relation === "north" ? own[0] < reference[0] : own[0] > reference[0];
    }
    if (statement.type === "relative_column_order") {
      return args.relation === "west" ? own[1] < reference[1] : own[1] > reference[1];
    }
    if (statement.type === "relative_row_distance") return own[0] - reference[0] === args.delta;
    if (statement.type === "relative_column_distance") return own[1] - reference[1] === args.delta;
    return null;
  }

  function evaluate() {
    let complete = Object.keys(positions).length === puzzle.characters.length;
    let valid = complete;
    for (const card of puzzle.cards) {
      for (const statement of card.statements) {
        const state = statementState(statement);
        const element = document.querySelector(`[data-statement="${statement.id}"]`);
        element.classList.toggle("satisfied", state === true);
        element.classList.toggle("violated", state === false);
        valid &&= state !== false;
        complete &&= state !== null;
      }
    }
    return { complete, valid };
  }

  function render() {
    cells.forEach((cell) => {
      cell.querySelector(".character-token")?.remove();
      cell.classList.remove("duplicate-row", "duplicate-column");
    });
    for (const [character, [row, column]] of Object.entries(positions)) {
      const cell = document.querySelector(`td[data-row="${row}"][data-column="${column}"]`);
      const token = document.createElement("span");
      token.className = "character-token";
      token.textContent = names[character].slice(0, 1);
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
    evaluate();
    save();
  }

  function place(cell) {
    const row = Number(cell.dataset.row);
    const column = Number(cell.dataset.column);
    if (blocked.has(key(row, column))) {
      status.value = "Ese mueble bloquea la casilla";
      return;
    }
    snapshot();
    if (positions[selected]?.[0] === row && positions[selected]?.[1] === column) {
      delete positions[selected];
      render();
      status.value = `${names[selected]} retirado`;
      return;
    }
    const occupant = Object.entries(positions).find(([, position]) => position[0] === row && position[1] === column);
    if (occupant && occupant[0] !== selected) delete positions[occupant[0]];
    positions[selected] = [row, column];
    render();
    status.value = `${names[selected]}: fila ${row + 1}, columna ${column + 1}`;
  }

  selectors.forEach((button) => button.addEventListener("click", () => {
    selected = button.dataset.character;
    render();
    status.value = `${names[selected]} seleccionado`;
  }));
  cells.forEach((cell) => {
    cell.addEventListener("click", () => place(cell));
    cell.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        place(cell);
      }
    });
  });
  document.querySelector('[data-action="undo"]').addEventListener("click", () => {
    if (history.length) positions = history.pop();
    render();
  });
  document.querySelector('[data-action="reset"]').addEventListener("click", () => {
    snapshot();
    positions = {};
    render();
    status.value = "Tablero reiniciado";
  });
  document.querySelector('[data-action="hint"]').addEventListener("click", () => {
    const pending = puzzle.cards
      .flatMap((card) => card.statements)
      .find((statement) => statementState(statement) !== true);
    if (!pending) {
      status.value = "Todas las declaraciones se cumplen";
      return;
    }
    metrics.hints += 1;
    saveMetrics();
    const clue = document.querySelector(`[data-statement="${pending.id}"]`);
    clue.closest(".card").scrollIntoView({ behavior: "smooth", block: "center" });
    clue.classList.add("hinted");
    setTimeout(() => clue.classList.remove("hinted"), 1800);
    status.value = "Revisa la declaración destacada";
  });
  document.querySelector('[data-action="check"]').addEventListener("click", () => {
    const result = evaluate();
    metrics.checks += 1;
    if (result.complete && !result.valid) metrics.errors += 1;
    if (result.complete && result.valid && !metrics.completedAt) metrics.completedAt = Date.now();
    saveMetrics();
    status.value = result.complete && result.valid
      ? "Caso resuelto"
      : result.complete ? "Hay pistas que no se cumplen" : "Faltan personajes por colocar";
  });

  restore();
  render();
})();
