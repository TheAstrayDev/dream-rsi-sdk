/* Bundled, dependency-free viewer. Recorded content is always rendered as text. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const offline = $('offline-state');
  const ui = { snapshot: {runs: [], events: []}, events: [], live: true, cursor: 0,
    requestedRun: null, selected: null, follow: true, collapsed: new Set(),
    preview: null, playing: false, transform: {x: 30, y: 30, k: 1}, runId: null,
    graphNodes: new Map(), graphEdges: new Map(), positions: new Map() };
  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = String(text);
    return el;
  }
  function svg(tag, attributes, text) {
    const el = document.createElementNS(NS, tag);
    Object.entries(attributes || {}).forEach(([key, value]) => el.setAttribute(key, value));
    if (text !== undefined) el.textContent = String(text);
    return el;
  }
  const number = value => typeof value === 'number' && Number.isFinite(value);
  const format = value => number(value) ? (value === 0 ? '0' : Math.abs(value) < .001
    ? value.toExponential(2) : Number(value.toPrecision(4)).toLocaleString('en-US', {maximumFractionDigits: 5})) : '—';
  const clock = seconds => `${Math.floor(Math.max(0, seconds) / 60)}:${String(Math.floor(Math.max(0, seconds) % 60)).padStart(2, '0')}`;
  const pretty = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  const titles = {run_opened: 'Run opened', node_snapshot: 'Answer recorded', policy_decision: 'Policy chose branches',
    attempt_started: 'Attempt dispatched', attempt_finished: 'Attempt finished', usage: 'Usage settled',
    run_result: 'Run completed', run_failed: 'Run interrupted', dream_started: 'Replay started',
    dream_completed: 'Replay completed', policy_review: 'Policy reviewed', policy_promoted: 'Policy promoted',
    policy_rejected: 'Policy rejected', replay_comparison: 'Offline comparison', budget_exhausted: 'Budget reached'};

  function project(events) {
    const view = {nodes: new Map(), attempts: new Map(), decisions: [], reviews: [], comparisons: [],
      meta: {}, usage: null, result: null, status: 'Running'};
    for (const event of events) {
      const data = event.data || {};
      switch (event.type) {
        case 'run_opened': view.meta = data; break;
        case 'node_snapshot': {
          const node = {...data.node};
          if (!node.id) break;
          const matches = [...view.attempts.entries()].filter(([, attempt]) =>
            attempt.parent_id === node.parent_id && attempt.finished);
          const pending = matches.find(([id]) => id === node.attempt_id) || matches[0];
          node.latency_ms = pending && (node.attempt_id || matches.length === 1) ? pending[1].latency_ms : null;
          if (pending) view.attempts.delete(pending[0]);
          view.nodes.set(node.id, node);
          break;
        }
        case 'attempt_started':
          if (data.attempt_id) view.attempts.set(data.attempt_id, {...data, started: event.timestamp});
          break;
        case 'attempt_finished': {
          const attempt = view.attempts.get(data.attempt_id);
          if (attempt) Object.assign(attempt, {finished: true, latency_ms: data.latency_ms});
          break;
        }
        case 'policy_decision': view.decisions.push(data); break;
        case 'usage': view.usage = data; if (data.run_spent) view.runSpent = data.run_spent; break;
        case 'run_result': view.result = data; view.status = 'Completed'; view.attempts.clear(); break;
        case 'run_failed': view.status = 'Interrupted'; view.attempts.clear(); break;
        case 'policy_review': view.reviews.push(data); break;
        case 'replay_comparison': view.comparisons.push(...(data.reports || [])); break;
        case 'dream_started': view.phase = 'Replay'; break;
        case 'dream_completed': view.phase = null; break;
      }
    }
    view.comparisons = view.comparisons.filter(report => report.tree_id === view.meta.tree_id);
    const useRaw = !!view.meta.quality_contract;
    const quality = node => {
      if (node.status === 'failed' || node.status === 'skipped') return null;
      const evaluationStatus = node.evaluation_status ?? node.metadata?.evaluation?.status;
      if (evaluationStatus && evaluationStatus !== 'PASSED') return null;
      return useRaw ? node.raw_quality ?? node.metadata?.quality_contract?.raw_quality : node.score;
    };
    view.quality = quality;
    view.best = view.result?.best_node_id ? view.nodes.get(view.result.best_node_id) :
      [...view.nodes.values()].filter(node => number(quality(node)))
        .sort((a, b) => quality(b) - quality(a) || a.order - b.order)[0];
    view.raw = view.result ? view.result.metrics?.raw_quality : view.best && quality(view.best);
    return view;
  }

  function updateRuns(snapshot) {
    const list = $('runs'), select = $('mobile-runs');
    const signature = snapshot.runs.map(run => run.id).join('|') + '|' + snapshot.selected_run;
    if (list.dataset.signature === signature) return;
    list.dataset.signature = signature;
    list.replaceChildren(); select.replaceChildren();
    $('run-count').textContent = snapshot.runs.length;
    for (const run of snapshot.runs) {
      const name = run.task?.name || 'Recorded search';
      const shortId = run.id.slice(0, 6);
      const button = element('button', `run-item${run.id === snapshot.selected_run ? ' selected' : ''}`);
      const label = element('span', 'run-name', `${shortId} · ${name}`);
      button.append(label, element('span', 'run-meta', new Date(run.timestamp * 1000).toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit'}) + ' · ' + (run.policy || 'Policy')));
      button.title = name;
      button.setAttribute('aria-current', run.id === snapshot.selected_run ? 'true' : 'false');
      button.addEventListener('click', () => chooseRun(run.id)); list.append(button);
      const option = element('option', '', shortId);
      option.value = run.id; option.selected = run.id === snapshot.selected_run; select.append(option);
    }
  }
  function chooseRun(id) { ui.requestedRun = id; ui.live = true; ui.playing = false; poll(); }

  function ingest(snapshot) {
    if (snapshot.error) throw new Error(snapshot.error);
    ui.snapshot = snapshot;
    if (snapshot.selected_run !== ui.runId) {
      ui.runId = snapshot.selected_run; ui.selected = null; ui.collapsed.clear(); ui.preview = null;
      ui.graphNodes.clear(); ui.graphEdges.clear(); $('nodes').replaceChildren(); $('edges').replaceChildren();
      ui.follow = true; ui.live = true; ui.playing = false; ui.cursor = 0;
      $('details').classList.remove('open');
    }
    const first = snapshot.events?.find(event => event.type === 'run_opened');
    ui.events = (snapshot.events || []).filter(event => !first || event.seq >= first.seq);
    if (ui.live) ui.cursor = Math.max(0, ui.events.length - 1);
    else ui.cursor = Math.min(ui.cursor, Math.max(0, ui.events.length - 1));
    updateRuns(snapshot);
    render();
  }

  function render() {
    const events = ui.events.slice(0, ui.cursor + 1);
    const view = project(events); ui.view = view;
    const hasRun = !!ui.runId;
    const demo = view.meta.task?.demo === true;
    const label = view.meta.task?.name || (hasRun ? 'Recorded search' : 'Your search, made visible.');
    $('session-title').textContent = hasRun ? `Run ${ui.runId.slice(0, 8)} / ${view.meta.policy || 'Policy'}` : 'Waiting for a run';
    $('run-title').textContent = label;
    $('run-kind').textContent = demo ? 'LOCAL SIMULATION · NO LLM REQUESTS' : view.meta.purpose === 'preparation' ? 'POLICY PREPARATION' : 'RECORDED EXECUTION';
    $('run-status').textContent = hasRun ? (view.phase || view.status) : 'Waiting';
    $('run-status').className = 'status-pill ' + (view.status === 'Completed' ? 'complete' : view.status === 'Interrupted' ? 'failed' : hasRun ? 'active' : '');
    $('quality-label').textContent = view.meta.quality_contract ? 'Raw quality' : 'Evaluator score';
    $('quality').textContent = format(view.raw);
    $('quality-note').textContent = view.best ? `Best found · ${nodeName(view.best)}` : 'No evaluated answer yet';
    const usage = view.usage;
    $('calls-label').textContent = demo ? 'SDK dispatches' : 'All-in call ledger';
    $('calls').textContent = usage ? Number((usage.spent?.total_llm_calls || 0) + (usage.held?.total_llm_calls || 0) + (usage.historical || 0)).toLocaleString() : '—';
    $('calls').title = 'Settled calls plus reservations for in-flight work and declared historical preparation.';
    const active = [...view.attempts.values()].filter(attempt => !attempt.finished).length;
    $('calls-note').textContent = usage ? `${usage.preparation + (usage.historical || 0)} prep · ${usage.deployment} application${active ? ' · ' + active + ' in flight' : ''}` : 'Usage not settled yet';
    const capKey = view.meta.budget?.total_llm_calls != null ? 'total_llm_calls' : 'model_calls';
    const cap = view.meta.budget?.[capKey];
    const spent = usage?.run_spent?.[capKey] ?? view.result?.costs?.[capKey];
    const reserved = usage?.run_held?.[capKey] || 0;
    $('budget-note').textContent = cap == null ? 'Run call cap: unlimited' :
      `Run ledger ${number(spent) ? spent + reserved : reserved} / ${cap}`;
    $('budget-note').title = 'Settled calls and current reservations against this run’s call cap.';
    $('tokens').textContent = usage?.tokens == null || usage.historical ? 'Unknown' : Number(usage.tokens).toLocaleString();
    $('usd').textContent = usage?.usd == null || usage.historical ? 'Cost not reported' : '$' + usage.usd.toFixed(4) + ' reported';
    const problems = [];
    if (demo) problems.push('Deterministic SDK demonstration. No model requests; not a benchmark.');
    if (ui.snapshot.dropped) problems.push(`${ui.snapshot.dropped} observation events dropped. History is incomplete.`);
    if (ui.snapshot.truncated) problems.push('Only the latest 10,000 events are shown. History is incomplete.');
    if (ui.events.some(event => event.data?._projection_limited || event.data?._truncated)) problems.push('Some recorded content exceeded the capture limit. Detailed history is incomplete.');
    const writerStopped = !offline && ui.snapshot.writer_alive === false && view.status === 'Running';
    if (writerStopped) problems.push('The writer stopped before this run closed. Its final outcome is unknown.');
    if (writerStopped && ui.live) {$('run-status').textContent = 'Unclosed'; $('run-status').className = 'status-pill';}
    if (offline && view.status === 'Running') {
      problems.push('Saved before this run closed. Later outcomes are not included.');
      $('run-status').textContent = 'Recorded in flight'; $('run-status').className = 'status-pill';
    }
    document.body.classList.toggle('writer-stopped', writerStopped);
    $('notice').hidden = !problems.length; $('notice').textContent = problems.join(' ');
    $('empty').hidden = view.nodes.size > 0;
    $('graph-caption').hidden = !view.nodes.size;
    drawGraph(view);
    drawDetails(view);
    drawComparisons(view);
    drawTimeline(events);
    $('follow').classList.toggle('toggled', ui.follow); $('follow').setAttribute('aria-pressed', String(ui.follow));
    $('export').disabled = !hasRun || !!offline;
  }

  function nodeName(node) { return node.ghost ? 'Active attempt' : node.parent_id == null ? 'Initial state' : `Node ${String(node.order).padStart(2, '0')}`; }
  function graphData(view) {
    const nodes = new Map(view.nodes);
    for (const [id, attempt] of view.attempts) {
      const parent = nodes.get(attempt.parent_id);
      if (!parent) continue;
      nodes.set('attempt:' + id, {id: 'attempt:' + id, parent_id: parent.id, depth: parent.depth + 1,
        ghost: true, status: attempt.finished ? 'waiting' : 'active', attempt, order: Infinity});
    }
    const children = new Map([...nodes.keys()].map(id => [id, []]));
    const roots = [], warnings = [];
    for (const node of nodes.values()) {
      if (node.parent_id == null) roots.push(node);
      else if (children.has(node.parent_id)) children.get(node.parent_id).push(node);
      else { roots.push(node); warnings.push('Missing parent'); }
      if (node.score != null && !number(node.score)) warnings.push('Invalid score');
    }
    const visible = [], visited = new Set(), pos = new Map(); let leaf = 0;
    function visit(node, depth) {
      if (visited.has(node.id)) { warnings.push('Repeated link'); return null; }
      if (visible.length >= 400 || depth > 40) return null;
      visited.add(node.id); visible.push(node);
      const branch = ui.collapsed.has(node.id) ? [] : children.get(node.id);
      const ys = branch.map(child => visit(child, depth + 1)).filter(y => y !== null);
      const y = ys.length ? (ys[0] + ys[ys.length - 1]) / 2 : 35 + leaf++ * 122;
      pos.set(node.id, {x: depth * 230 + 25, y}); return y;
    }
    roots.forEach(node => visit(node, 0));
    if (visible.length < nodes.size && !ui.collapsed.size) warnings.push('Some nodes hidden · collapse branches to explore');
    return {visible, pos, children, warnings: [...new Set(warnings)], total: nodes.size};
  }

  function drawGraph(view) {
    const data = graphData(view); ui.positions = data.pos; ui.graphData = data;
    const activePath = new Set();
    for (const node of data.visible.filter(n => n.status === 'active')) {
      let current = node; const seen = new Set();
      while (current && !seen.has(current.id)) {
        seen.add(current.id); activePath.add(current.id); current = view.nodes.get(current.parent_id);
      }
    }
    const bestPath = new Set(); let best = view.best;
    while (best && !bestPath.has(best.id)) { bestPath.add(best.id); best = view.nodes.get(best.parent_id); }
    const visibleIds = new Set(data.visible.map(node => node.id));
    for (const [id, el] of ui.graphNodes) if (!visibleIds.has(id)) {el.remove(); ui.graphNodes.delete(id);}
    for (const [id, el] of ui.graphEdges) if (!visibleIds.has(id)) {el.remove(); ui.graphEdges.delete(id);}
    for (const node of data.visible) {
      const point = data.pos.get(node.id), parent = data.pos.get(node.parent_id);
      if (parent) {
        let group = ui.graphEdges.get(node.id);
        if (!group) { group = svg('g'); group.append(svg('path'), svg('path')); $('edges').append(group); ui.graphEdges.set(node.id, group); }
        const path = `M${parent.x + 155},${parent.y + 36} C${parent.x + 190},${parent.y + 36} ${point.x - 35},${point.y + 36} ${point.x},${point.y + 36}`;
        const running = activePath.has(node.id) && ui.live && !offline && !ui.preview;
        group.children[0].setAttribute('d', path); group.children[1].setAttribute('d', path);
        group.children[0].setAttribute('class', 'edge' + (running ? ' active' : bestPath.has(node.id) ? ' best' : ''));
        group.children[1].setAttribute('class', 'edge signal'); group.children[1].style.display = running ? '' : 'none';
        group.style.opacity = ui.preview && !ui.preview.has(node.id) ? '.22' : '1';
      }
      let el = ui.graphNodes.get(node.id);
      if (!el) {
        el = svg('g', {class: 'node node-entry', tabindex: '0', role: 'button', 'data-node-id': node.id});
        el.append(svg('rect', {class: 'node-body', x: 0, y: 0, width: 155, height: 74, rx: 6}),
          svg('circle', {class: 'node-ring', cx: 16, cy: 17, r: 3}),
          svg('circle', {class: 'node-dot', cx: 16, cy: 17, r: 3}),
          svg('text', {class: 'node-title', x: 27, y: 21}),
          svg('text', {class: 'node-score', x: 13, y: 47}),
          svg('text', {class: 'node-sub', x: 13, y: 62}));
        el.addEventListener('click', event => { event.stopPropagation(); selectNode(node.id); });
        el.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); selectNode(node.id);} });
        $('nodes').append(el); ui.graphNodes.set(node.id, el);
      }
      el.setAttribute('transform', `translate(${point.x},${point.y})`);
      el.setAttribute('class', `node ${node.status}${node.id === view.best?.id ? ' best' : ''}${node.id === ui.selected ? ' selected' : ''}`);
      el.setAttribute('aria-label', `${nodeName(node)}, ${node.status}, quality ${format(view.quality(node))}`);
      el.children[1].style.display = node.status === 'active' && ui.live && !offline ? '' : 'none';
      el.children[3].textContent = nodeName(node);
      el.children[4].textContent = node.ghost ? (node.status === 'waiting' ? 'Awaiting batch' : ui.live && !offline ? 'Working…' : 'Recorded in flight') : node.status === 'failed' ? 'Failed' : format(view.quality(node));
      el.children[4].style.fontSize = node.ghost || node.status === 'failed' ? '12px' : '';
      el.children[5].textContent = node.ghost ? 'Actual dispatched attempt' : node.parent_id == null ? 'Starting workspace' : `Depth ${node.depth} · ${node.status}`;
      el.style.opacity = ui.preview && !ui.preview.has(node.id) && node.parent_id != null ? '.32' : '1';
      let fold = el.querySelector('.fold-control');
      if (data.children.get(node.id).length) {
        if (!fold) {
          fold = svg('g', {class: 'fold-control', role: 'button', tabindex: '0', 'aria-label': 'Collapse or expand descendants'});
          fold.append(svg('circle', {class: 'fold-toggle', cx: 155, cy: 36, r: 8}), svg('text', {class: 'fold-label', x: 155, y: 39, 'text-anchor': 'middle'}));
          const toggle = event => {event.stopPropagation(); event.preventDefault(); ui.collapsed.has(node.id) ? ui.collapsed.delete(node.id) : ui.collapsed.add(node.id); render();};
          fold.addEventListener('click', toggle); fold.addEventListener('keydown', event => {if (event.key === 'Enter' || event.key === ' ') toggle(event);}); el.append(fold);
        }
        fold.children[1].textContent = ui.collapsed.has(node.id) ? '+' : '−';
      } else if (fold) fold.remove();
    }
    $('node-count').textContent = `${view.nodes.size} recorded nodes${view.attempts.size ? ' · ' + view.attempts.size + ' pending' : ''}`;
    $('tree-warning').textContent = data.warnings.join(' · ');
    if (ui.follow && data.visible.length) fitGraph(false);
    transformGraph();
  }
  function transformGraph() {
    const t = ui.transform;
    $('world').setAttribute('transform', `translate(${t.x},${t.y}) scale(${t.k})`);
    const overview = t.k < .65;
    $('graph-shell').classList.toggle('overview', overview);
    for (const node of ui.graphData?.visible || []) {
      const label = ui.graphNodes.get(node.id)?.children[3];
      if (label) label.textContent = overview ? node.ghost ? node.status === 'active' ? 'Active' : 'Batch' : node.parent_id == null ? 'Start' : `Node ${node.order}` : nodeName(node);
    }
  }
  function fitGraph(force = true) {
    const points = [...ui.positions.values()]; if (!points.length) return;
    const width = $('graph').clientWidth, height = $('graph').clientHeight;
    const minY = Math.min(...points.map(p => p.y)), maxY = Math.max(...points.map(p => p.y)) + 74;
    const right = Math.max(...points.map(p => p.x)) + 180;
    const k = Math.min(1.1, Math.max(.22, Math.min((width - 65) / right, (height - 75) / (maxY - minY))));
    ui.transform = {k, x: (width - right * k) / 2 + 10, y: (height - (maxY - minY) * k) / 2 - minY * k};
    if (!force && k < .65) {
      const focus = [...ui.graphData.visible].reverse().find(node => node.status === 'active') || ui.view.best || ui.graphData.visible.at(-1);
      const point = focus && ui.positions.get(focus.id);
      if (point) {
        const zoom = Math.min(width < 600 ? .9 : .8, (width - 48) / 385);
        const running = ui.graphData.visible.filter(node => node.status === 'active').map(node => ui.positions.get(node.id));
        const centerY = running.length ? running.reduce((sum, p) => sum + p.y + 37, 0) / running.length : point.y + 37;
        ui.transform = {k: zoom, x: width / 2 - (point.x - 38) * zoom, y: height / 2 - centerY * zoom};
      }
    }
    if (force) {
      ui.follow = false;
      $('follow').classList.remove('toggled'); $('follow').setAttribute('aria-pressed', 'false');
      transformGraph();
    }
  }
  function zoom(factor, x = $('graph').clientWidth / 2, y = $('graph').clientHeight / 2) {
    const old = ui.transform.k, next = Math.max(.15, Math.min(3, old * factor));
    ui.transform.x = x - (x - ui.transform.x) * next / old;
    ui.transform.y = y - (y - ui.transform.y) * next / old; ui.transform.k = next; ui.follow = false;
    $('follow').classList.remove('toggled'); $('follow').setAttribute('aria-pressed', 'false'); transformGraph();
  }

  function selectNode(id) {ui.selected = id; $('details').classList.add('open'); render();}
  function section(title) {const el = element('section', 'detail-section'); el.append(element('h4', '', title)); return el;}
  function drawDetails(view) {
    const node = view.nodes.get(ui.selected) || ui.graphData?.visible.find(n => n.id === ui.selected);
    $('detail-empty').hidden = !!node; $('detail-content').hidden = !node;
    if (!node) return;
    const signature = JSON.stringify([node, view.decisions, view.best?.id]);
    const target = $('detail-content'); if (target.dataset.signature === signature) return;
    target.dataset.signature = signature; target.replaceChildren();
    const top = element('div', 'detail-top'); top.append(element('h3', '', nodeName(node)), element('span', 'status-pill', node.status));
    target.append(top, element('p', 'detail-id', node.id));
    const score = element('div', 'detail-score'); score.append(element('span', 'metric-label', view.meta.quality_contract ? 'Raw quality' : 'Evaluator score'), element('strong', '', format(view.quality(node)))); target.append(score);
    const answer = section(node.parent_id == null ? 'Initial workspace' : 'Recorded answer');
    const value = node.parent_id == null ? (node.observation ?? node.state) : node.observation;
    if (node.ghost) answer.append(element('p', 'muted', node.attempt.finished ? 'The request finished. Its result will be revealed when the complete batch is recorded.' : 'This attempt has actually been dispatched. No answer has been recorded yet.'));
    else if (value == null) answer.append(element('p', 'muted', 'No answer was recorded.'));
    else if (typeof value === 'object' && !Array.isArray(value) && Object.values(value).every(v => v == null || typeof v !== 'object')) {
      const list = element('dl', 'answer-properties');
      for (const [key, val] of Object.entries(value)) {const item = element('div'); item.append(element('dt', '', key), element('dd', '', String(val))); list.append(item);} answer.append(list);
    } else answer.append(element('pre', 'answer-box', pretty(value)));
    target.append(answer);
    if (node.metadata?.error) {const error = section('Recorded error'); error.append(element('p', 'detail-error', node.metadata.error)); target.append(error);}
    const decision = [...view.decisions].reverse().find(d => d.expand?.includes(node.parent_id || node.id));
    const explanation = section('Policy decision');
    if (decision) {
      explanation.append(element('p', 'decision-note', decision.reason || `${decision.policy} selected this parent in round ${decision.round}. No explanation was supplied by the policy.`));
    } else explanation.append(element('p', 'muted', node.parent_id == null ? 'The root is the initial state, not a generated answer.' : 'No policy decision was recorded for this node.'));
    target.append(explanation);
    const facts = element('div', 'detail-grid');
    for (const [label, text] of [['Depth', node.depth], ['Children', ui.graphData.children.get(node.id)?.length || 0], ['Elapsed', number(node.latency_ms) ? (node.latency_ms / 1000).toFixed(2) + ' s' : 'Not reported'], ['Selection', node.id === view.best?.id ? 'Best found' : 'Recorded candidate']]) {
      const item = element('div'); item.append(element('span', '', label), element('strong', '', text)); facts.append(item);
    } target.append(facts);
    const details = element('details'); details.style.marginTop = '23px'; details.append(element('summary', '', 'Recorded diagnostics'), element('pre', '', pretty(node.metadata || {}))); target.append(details);
  }

  const clearPreview = element('button', 'button small', 'Clear replay path'); clearPreview.hidden = true;
  clearPreview.addEventListener('click', () => {ui.preview = null; clearPreview.hidden = true; render();}); document.querySelector('.graph-actions').prepend(clearPreview);
  function drawComparisons(view) {
    $('comparison-count').hidden = !view.comparisons.length; $('comparison-count').textContent = view.comparisons.length;
    $('comparison-empty').hidden = !!view.comparisons.length;
    const signature = JSON.stringify([view.comparisons, view.reviews]);
    const target = $('comparisons'); if (target.dataset.signature === signature) return;
    target.dataset.signature = signature; target.replaceChildren(); $('policy-reviews').replaceChildren();
    if (view.comparisons.length) {
      const grid = element('div', 'comparison-grid');
      for (const report of view.comparisons) {
        const card = element('div', 'comparison-card'); card.append(element('h3', '', report.policy), element('strong', 'comparison-quality', format(report.raw_quality)),
          element('p', '', 'Revealed quality'), element('p', '', `${report.probes} recorded probes · ${report.attempted} attempted expansions`),
          element('p', report.missing ? 'warning' : '', `${report.missing} unrecorded continuations · offline SDK replay`));
        if (report.preserves_original) card.append(element('p', 'warning', `Requested ${report.requested_policy}; quality contract keeps the original policy.`));
        const button = element('button', 'button small', 'Show recorded path');
        button.addEventListener('click', () => {ui.preview = new Set(report.revealed); ui.follow = false; ui.collapsed.clear(); clearPreview.hidden = false; chooseTab('tree'); render(); fitGraph();});
        card.append(button); grid.append(card);
      } target.append(grid, element('p', 'comparison-world', `World ${view.meta.tree_id?.slice(0, 12) || 'unknown'} · finite replay evidence, not unseen-task validation`));
    }
    for (const review of view.reviews) {
      const outcome = typeof review.outcome === 'string' ? review.outcome : 'unknown';
      const card = element('div', 'review' + (outcome === 'REJECTED' ? ' rejected' : ''));
      card.append(element('h3', '', `Policy ${outcome.toLowerCase()}`), element('p', '', review.reason || 'No review reason recorded.'));
      if (review.evidence) {
        const evidence = element('details');
        evidence.append(element('summary', '', 'Recorded promotion evidence'), element('pre', '', pretty(review.evidence)));
        card.append(evidence);
      }
      $('policy-reviews').append(card);
    }
  }
  function drawTimeline(events) {
    const last = events[events.length - 1], first = ui.events[0];
    $('scrubber').max = Math.max(0, ui.events.length - 1); $('scrubber').value = ui.cursor;
    $('timeline-mode').textContent = ui.playing ? 'Playing history' : ui.live ? offline ? 'Saved report' : 'Live view' : 'History';
    $('event-label').textContent = last ? titles[last.type] || last.type.replaceAll('_', ' ') : 'Waiting for events';
    $('time-current').textContent = last && first ? clock(last.timestamp - first.timestamp) : '0:00';
    $('play').textContent = ui.playing ? 'Ⅱ' : '▶'; $('play').setAttribute('aria-label', ui.playing ? 'Pause recorded history' : 'Play recorded history');
    $('go-live').disabled = ui.live && !ui.playing;
  }
  function chooseTab(tab) {
    for (const name of ['tree', 'policy']) {const active = tab === name; $(name + '-tab').classList.toggle('selected', active); $(name + '-tab').setAttribute('aria-selected', String(active)); $(name + '-view').hidden = !active;}
    if (tab === 'tree') requestAnimationFrame(() => {if (ui.follow) {fitGraph(false); transformGraph();}});
  }
  $('tree-tab').addEventListener('click', () => chooseTab('tree')); $('policy-tab').addEventListener('click', () => chooseTab('policy'));
  $('mobile-runs').addEventListener('change', event => chooseRun(event.target.value));
  $('fit').addEventListener('click', () => fitGraph()); $('zoom-in').addEventListener('click', () => zoom(1.2)); $('zoom-out').addEventListener('click', () => zoom(1 / 1.2));
  $('follow').addEventListener('click', () => {ui.follow = !ui.follow; render();});
  $('close-details').addEventListener('click', () => {ui.selected = null; $('details').classList.remove('open'); render();});
  $('scrubber').addEventListener('input', event => {ui.live = false; ui.playing = false; ui.cursor = Number(event.target.value); ui.preview = null; clearPreview.hidden = true; render();});
  $('go-live').addEventListener('click', () => {ui.live = true; ui.playing = false; ui.cursor = Math.max(0, ui.events.length - 1); render();});
  $('play').addEventListener('click', () => {ui.playing = !ui.playing; ui.live = false; if (ui.cursor >= ui.events.length - 1) ui.cursor = 0; render();});
  setInterval(() => {if (ui.playing) {if (ui.cursor < ui.events.length - 1) ui.cursor++; else ui.playing = false; render();}}, 180);
  $('export').addEventListener('click', () => {if (!offline && ui.runId) location.href = '/api/export?run=' + encodeURIComponent(ui.runId);});
  let drag = null;
  $('graph').addEventListener('pointerdown', event => {if (event.target.closest('.node')) return; drag = {px: event.clientX, py: event.clientY, tx: ui.transform.x, ty: ui.transform.y}; $('graph').setPointerCapture(event.pointerId); $('graph').classList.add('dragging');});
  $('graph').addEventListener('pointermove', event => {if (!drag || drag.px === undefined) return; ui.follow = false; ui.transform.x = drag.tx + event.clientX - drag.px; ui.transform.y = drag.ty + event.clientY - drag.py; transformGraph(); $('follow').classList.remove('toggled'); $('follow').setAttribute('aria-pressed', 'false');});
  const endDrag = () => {drag = null; $('graph').classList.remove('dragging');};
  $('graph').addEventListener('pointerup', endDrag); $('graph').addEventListener('pointercancel', endDrag);
  $('graph').addEventListener('wheel', event => {event.preventDefault(); const rect = $('graph').getBoundingClientRect(); zoom(Math.exp(-event.deltaY * .0015), event.clientX - rect.left, event.clientY - rect.top);}, {passive: false});
  $('graph').addEventListener('keydown', event => {if (event.target !== $('graph')) return; if (event.key === '+' || event.key === '=') {event.preventDefault(); zoom(1.2);} if (event.key === '-') {event.preventDefault(); zoom(1 / 1.2);} if (event.key === '0') fitGraph();});
  document.addEventListener('keydown', event => {if (event.key === 'Escape') {$('close-details').click();} });
  new ResizeObserver(() => {if (ui.follow) {fitGraph(false); transformGraph();}}).observe($('graph-shell'));

  let pollVersion = 0;
  async function poll() {
    if (offline) return;
    const version = ++pollVersion;
    try {
      const response = await fetch('/api/state' + (ui.requestedRun ? '?run=' + encodeURIComponent(ui.requestedRun) : ''), {cache: 'no-store'});
      if (!response.ok) throw new Error('Inspector journal is unavailable. Check its path or restart the writer.');
      const snapshot = await response.json();
      if (version !== pollVersion) return;
      ingest(snapshot);
      $('connection').classList.remove('offline'); $('connection').replaceChildren(element('i'), document.createTextNode(snapshot.writer_alive ? 'Local connection' : snapshot.runs.length ? 'Saved history' : 'Waiting for runtime'));
      document.body.classList.remove('disconnected');
    } catch (error) {
      $('connection').classList.add('offline'); $('connection').replaceChildren(element('i'), document.createTextNode('Disconnected'));
      $('notice').hidden = false; $('notice').textContent = error.message || 'Connection lost. Retrying…'; document.body.classList.add('disconnected');
    }
  }
  if (offline) {
    try {ingest(JSON.parse(offline.textContent)); $('connection').replaceChildren(element('i'), document.createTextNode('Saved report'));}
    catch { $('notice').hidden = false; $('notice').textContent = 'This saved report is not valid.'; }
  } else {poll(); setInterval(poll, 1000);}
})();
