#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');

function loadOptional(name) {
  try {
    return require(name);
  } catch {
    return null;
  }
}

const ts = loadOptional('typescript');
const postcss = loadOptional('postcss');
const parse5 = loadOptional('parse5');

function printJson(obj) {
  process.stdout.write(JSON.stringify(obj));
}

function readStdin() {
  return fs.readFileSync(0, 'utf8');
}

function safeTrim(text, maxLen = 160) {
  const compact = String(text || '').replace(/\s+/g, ' ').trim();
  return compact.length > maxLen ? compact.slice(0, maxLen - 3) + '...' : compact;
}

function lineOf(sourceFile, node) {
  const pos = typeof node.getStart === 'function' ? node.getStart(sourceFile, false) : 0;
  return sourceFile.getLineAndCharacterOfPosition(pos).line + 1;
}

function relPath(projectRoot, absolutePath) {
  return path.relative(projectRoot, absolutePath).split(path.sep).join('/');
}

function resolveProjectRelative(projectRoot, filePath, spec, candidates) {
  if (!spec || /^(?:https?:)?\/\//.test(spec) || spec.startsWith('data:')) {
    return spec || null;
  }
  const tries = [];
  const addPath = (p) => { if (p) tries.push(p); };
  if (spec.startsWith('/')) {
    addPath(path.join(projectRoot, spec.slice(1)));
  } else {
    addPath(path.resolve(path.dirname(filePath), spec));
    addPath(path.resolve(projectRoot, spec));
  }
  const raw = [...tries];
  for (const candidate of raw) {
    if (path.extname(candidate)) {
      addPath(candidate);
    } else {
      for (const ext of candidates) addPath(candidate + ext);
      addPath(path.join(candidate, '__init__.py'));
      addPath(path.join(candidate, 'index.js'));
      addPath(path.join(candidate, 'index.jsx'));
      addPath(path.join(candidate, 'index.ts'));
      addPath(path.join(candidate, 'index.tsx'));
      addPath(path.join(candidate, 'index.css'));
      addPath(path.join(candidate, 'index.html'));
    }
  }
  const seen = new Set();
  for (const candidate of tries) {
    if (seen.has(candidate)) continue;
    seen.add(candidate);
    try {
      if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
        return relPath(projectRoot, candidate);
      }
    } catch {}
  }
  return spec;
}

function markerForSuffix(suffix) {
  return suffix === '.html' ? '<!-- ... (body stripped by Qompressor) ... -->' : '// ... (body stripped by Qompressor) ...';
}

function simpleSelectorTokens(selectorValue) {
  const tokens = [];
  const text = String(selectorValue || '');
  const seen = new Set();
  const add = (kind, value) => {
    const key = `${kind}:${value}`;
    if (!value || seen.has(key)) return;
    seen.add(key);
    tokens.push({ kind, value });
  };
  for (const m of text.matchAll(/#([A-Za-z_][A-Za-z0-9_-]*)/g)) add('id', m[1]);
  for (const m of text.matchAll(/\.([A-Za-z_][A-Za-z0-9_-]*)/g)) add('class', m[1]);
  for (const part of text.split(/\s*,\s*/)) {
    const bare = part.trim().match(/^[A-Za-z][A-Za-z0-9_-]*/);
    if (bare) add('tag', bare[0]);
  }
  return tokens;
}

function jsScriptKind(ext) {
  if (!ts) return undefined;
  switch (ext) {
    case '.ts': return ts.ScriptKind.TS;
    case '.tsx': return ts.ScriptKind.TSX;
    case '.jsx': return ts.ScriptKind.JSX;
    case '.js':
    case '.mjs':
    case '.cjs':
    default: return ts.ScriptKind.JS;
  }
}

function readNodeText(sourceFile, node, maxLen = 220) {
  return safeTrim(node.getText(sourceFile), maxLen);
}

function headerUntilBody(sourceFile, node, bodyNode) {
  if (!bodyNode) return readNodeText(sourceFile, node);
  const start = node.getStart(sourceFile, false);
  const end = bodyNode.getStart(sourceFile, false);
  return safeTrim(sourceFile.text.slice(start, end).trimEnd() + ' {', 220);
}

function isExported(node) {
  return !!(node.modifiers || []).find(m => m.kind === ts.SyntaxKind.ExportKeyword || m.kind === ts.SyntaxKind.DefaultKeyword);
}

function callSummary(sourceFile, node) {
  const calls = [];
  const selectors = [];
  const events = [];
  let readsStorage = false;
  let writesStorage = false;
  function pushUnique(arr, value, limit) {
    if (value && !arr.includes(value) && arr.length < limit) arr.push(value);
  }
  function visit(n) {
    if (ts.isCallExpression(n)) {
      const expr = n.expression;
      const calleeText = expr.getText(sourceFile);
      if (!['if', 'for', 'while', 'switch', 'catch'].includes(calleeText)) pushUnique(calls, safeTrim(calleeText, 40), 6);
      if (ts.isPropertyAccessExpression(expr)) {
        const owner = expr.expression.getText(sourceFile);
        const prop = expr.name.getText(sourceFile);
        if ((owner === 'document' || owner.endsWith('.document')) && ['querySelector', 'querySelectorAll', 'getElementById', 'getElementsByClassName'].includes(prop)) {
          const arg = n.arguments[0];
          if (arg && (ts.isStringLiteral(arg) || ts.isNoSubstitutionTemplateLiteral(arg))) {
            pushUnique(selectors, arg.text, 4);
          }
        }
        if (prop === 'addEventListener') {
          const arg = n.arguments[0];
          if (arg && (ts.isStringLiteral(arg) || ts.isNoSubstitutionTemplateLiteral(arg))) pushUnique(events, arg.text, 4);
        }
        if ((owner === 'localStorage' || owner === 'sessionStorage' || owner === 'window.localStorage' || owner === 'window.sessionStorage')) {
          if (['getItem', 'key'].includes(prop)) readsStorage = true;
          if (['setItem', 'removeItem', 'clear'].includes(prop)) writesStorage = true;
        }
      }
    }
    ts.forEachChild(n, visit);
  }
  ts.forEachChild(node, visit);
  const parts = [];
  if (calls.length) parts.push(`calls: ${calls.join(', ')}`);
  if (selectors.length) parts.push(`selectors: ${selectors.join(', ')}`);
  if (events.length) {
    parts.push(`events: ${events.join(', ')}`);
    parts.push(`listeners: ${events.map(event => `addEventListener("${event}")`).join(', ')}`);
  }
  if (readsStorage) parts.push('reads storage');
  if (writesStorage) parts.push('writes storage');
  return parts.length ? parts.join('; ') : 'implementation stripped';
}

function extractJsTs(projectRoot, filePath, rel, content) {
  if (!ts) throw new Error('typescript module unavailable');
  const ext = path.extname(filePath).toLowerCase();
  const sourceFile = ts.createSourceFile(filePath, content, ts.ScriptTarget.Latest, true, jsScriptKind(ext));
  const moduleNode = `module:${rel}`;
  const language = ['.ts', '.tsx'].includes(ext) ? 'typescript' : 'javascript';
  const symbols = [];
  const relationships = [];
  const imports = [];
  const localDefs = new Map();
  const importBindings = new Map();
  const classMethods = new Map();

  function addRelationship(edge) {
    relationships.push({ resolved: true, ...edge });
  }
  function addSymbol(symbol) {
    symbols.push(symbol);
    if (symbol.qualified_name && !localDefs.has(symbol.name)) localDefs.set(symbol.name, symbol.qualified_name);
  }

  function resolveImportTarget(spec) {
    return resolveProjectRelative(projectRoot, filePath, spec, ['.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx']);
  }

  function collectDecls(node, classQName = null) {
    if (ts.isImportDeclaration(node) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
      const spec = node.moduleSpecifier.text;
      const target = resolveImportTarget(spec);
      imports.push({ target, line: lineOf(sourceFile, node) });
      addRelationship({ type: 'imports', source: moduleNode, target, line: lineOf(sourceFile, node) });
      const clause = node.importClause;
      if (clause) {
        if (clause.name) importBindings.set(clause.name.text, { kind: 'default', target, imported: 'default' });
        if (clause.namedBindings) {
          if (ts.isNamespaceImport(clause.namedBindings)) {
            importBindings.set(clause.namedBindings.name.text, { kind: 'namespace', target });
          } else if (ts.isNamedImports(clause.namedBindings)) {
            for (const el of clause.namedBindings.elements) {
              importBindings.set(el.name.text, { kind: 'named', target, imported: (el.propertyName || el.name).text });
            }
          }
        }
      }
    } else if (ts.isExportDeclaration(node) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
      const target = resolveImportTarget(node.moduleSpecifier.text);
      imports.push({ target, line: lineOf(sourceFile, node) });
      addRelationship({ type: 'imports', source: moduleNode, target, line: lineOf(sourceFile, node) });
    } else if (ts.isClassDeclaration(node)) {
      const name = node.name ? node.name.text : 'default';
      const qname = `${rel}::${name}`;
      addSymbol({ name, type: 'class', line: lineOf(sourceFile, node), signature: headerUntilBody(sourceFile, node, node.members.pos ? node.members[0] : node), qualified_name: qname, metadata: {} });
      classMethods.set(qname, new Map());
      if (isExported(node)) addRelationship({ type: 'exports', source: moduleNode, target: qname, line: lineOf(sourceFile, node) });
      if (node.heritageClauses) {
        for (const hc of node.heritageClauses) {
          if (hc.token === ts.SyntaxKind.ExtendsKeyword) {
            for (const t of hc.types) {
              const exprText = t.expression.getText(sourceFile);
              const target = resolveRef(exprText, qname);
              addRelationship({ type: 'extends', source: qname, target, line: lineOf(sourceFile, t), resolved: target !== exprText });
            }
          }
          if (hc.token === ts.SyntaxKind.ImplementsKeyword) {
            for (const t of hc.types) {
              const exprText = t.expression.getText(sourceFile);
              const target = resolveRef(exprText, qname);
              addRelationship({ type: 'implements', source: qname, target, line: lineOf(sourceFile, t), resolved: target !== exprText });
            }
          }
        }
      }
      for (const member of node.members) collectDecls(member, qname);
    } else if (ts.isMethodDeclaration(node) || ts.isConstructorDeclaration(node) || ts.isGetAccessorDeclaration(node) || ts.isSetAccessorDeclaration(node)) {
      if (!classQName) return;
      const rawName = ts.isConstructorDeclaration(node) ? 'constructor' : node.name.getText(sourceFile);
      const qname = `${classQName}.${rawName}`;
      const signature = ts.isConstructorDeclaration(node)
        ? headerUntilBody(sourceFile, node, node.body)
        : headerUntilBody(sourceFile, node, node.body);
      symbols.push({ name: rawName, type: 'method', line: lineOf(sourceFile, node), signature, qualified_name: qname, parent: classQName, metadata: {} });
      classMethods.get(classQName).set(rawName, qname);
    } else if (ts.isFunctionDeclaration(node) && node.name) {
      const name = node.name.text;
      const qname = `${rel}::${name}`;
      addSymbol({ name, type: 'function', line: lineOf(sourceFile, node), signature: headerUntilBody(sourceFile, node, node.body), qualified_name: qname, metadata: {} });
      if (isExported(node)) addRelationship({ type: 'exports', source: moduleNode, target: qname, line: lineOf(sourceFile, node) });
    } else if (ts.isVariableStatement(node)) {
      for (const decl of node.declarationList.declarations) {
        if (!ts.isIdentifier(decl.name)) continue;
        const name = decl.name.text;
        const init = decl.initializer;
        if (init && (ts.isArrowFunction(init) || ts.isFunctionExpression(init))) {
          const qname = `${rel}::${name}`;
          addSymbol({ name, type: 'function', line: lineOf(sourceFile, decl), signature: safeTrim(`${name}${init.parameters ? init.parameters.map(p => p.getText(sourceFile)).join(', ') : ''}`, 180), qualified_name: qname, metadata: {} });
          if (isExported(node)) addRelationship({ type: 'exports', source: moduleNode, target: qname, line: lineOf(sourceFile, decl) });
        } else if (init && (ts.isStringLiteral(init) || ts.isNumericLiteral(init) || init.kind === ts.SyntaxKind.TrueKeyword || init.kind === ts.SyntaxKind.FalseKeyword)) {
          if (/^[A-Z0-9_]+$/.test(name)) {
            addSymbol({ name, type: 'variable', line: lineOf(sourceFile, decl), signature: safeTrim(decl.getText(sourceFile), 180), qualified_name: `${rel}::${name}`, metadata: { kind: 'constant' } });
          }
        } else if (init && ts.isObjectLiteralExpression(init) && isExported(node)) {
          addSymbol({ name, type: 'variable', line: lineOf(sourceFile, decl), signature: safeTrim(decl.getText(sourceFile), 180), qualified_name: `${rel}::${name}`, metadata: { kind: 'object_schema' } });
        }
      }
    } else if (ts.isInterfaceDeclaration(node)) {
      const name = node.name.text;
      symbols.push({ name, type: 'variable', line: lineOf(sourceFile, node), signature: readNodeText(sourceFile, node), qualified_name: `${rel}::${name}`, metadata: { kind: 'interface' } });
    } else if (ts.isTypeAliasDeclaration(node)) {
      const name = node.name.text;
      symbols.push({ name, type: 'variable', line: lineOf(sourceFile, node), signature: readNodeText(sourceFile, node), qualified_name: `${rel}::${name}`, metadata: { kind: 'type' } });
    } else if (ts.isEnumDeclaration(node)) {
      const name = node.name.text;
      symbols.push({ name, type: 'variable', line: lineOf(sourceFile, node), signature: readNodeText(sourceFile, node), qualified_name: `${rel}::${name}`, metadata: { kind: 'enum' } });
    }
    ts.forEachChild(node, child => collectDecls(child, classQName));
  }

  function resolveRef(name, classQName = null) {
    if (!name) return name;
    if (classQName && classMethods.get(classQName)?.has(name)) return classMethods.get(classQName).get(name);
    if (localDefs.has(name)) return localDefs.get(name);
    if (importBindings.has(name)) {
      const info = importBindings.get(name);
      if (info.kind === 'named') return `${info.target}::${info.imported}`;
      return info.target;
    }
    const dotted = name.split('.');
    if (dotted.length > 1 && importBindings.has(dotted[0])) {
      const info = importBindings.get(dotted[0]);
      return `${info.target}::${dotted.slice(1).join('.')}`;
    }
    return name;
  }

  collectDecls(sourceFile);

  function selectorSymbol(sourceQname, selectorValue, kind, line) {
    const safe = selectorValue.replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 24) || 'selector';
    return {
      name: selectorValue,
      type: 'selector',
      line,
      signature: selectorValue,
      qualified_name: `${sourceQname || moduleNode}::selector:${line}:${safe}`,
      parent: sourceQname || null,
      metadata: { selector_value: selectorValue, selector_kind: kind, simple_tokens: simpleSelectorTokens(selectorValue) },
    };
  }

  function collectRuntime(node, currentSource = moduleNode, classQName = null) {
    if (ts.isClassDeclaration(node)) {
      const qname = `${rel}::${node.name ? node.name.text : 'default'}`;
      for (const member of node.members) collectRuntime(member, qname, qname);
      return;
    }
    if (ts.isFunctionDeclaration(node) && node.name) {
      const qname = `${rel}::${node.name.text}`;
      if (node.body) collectRuntime(node.body, qname, classQName);
      return;
    }
    if (ts.isMethodDeclaration(node) || ts.isConstructorDeclaration(node) || ts.isGetAccessorDeclaration(node) || ts.isSetAccessorDeclaration(node)) {
      const rawName = ts.isConstructorDeclaration(node) ? 'constructor' : node.name.getText(sourceFile);
      const qname = classQName ? `${classQName}.${rawName}` : currentSource;
      if (node.body) collectRuntime(node.body, qname, classQName);
      return;
    }
    if (ts.isVariableStatement(node)) {
      for (const decl of node.declarationList.declarations) {
        if (ts.isIdentifier(decl.name) && decl.initializer && (ts.isArrowFunction(decl.initializer) || ts.isFunctionExpression(decl.initializer)) && decl.initializer.body) {
          const qname = `${rel}::${decl.name.text}`;
          collectRuntime(decl.initializer.body, qname, classQName);
        }
      }
    }
    if (ts.isCallExpression(node)) {
      const line = lineOf(sourceFile, node);
      const expr = node.expression;
      let handled = false;
      if (ts.isPropertyAccessExpression(expr)) {
        const ownerText = expr.expression.getText(sourceFile);
        const prop = expr.name.getText(sourceFile);
        if ((ownerText === 'document' || ownerText.endsWith('.document')) && ['querySelector', 'querySelectorAll', 'getElementById', 'getElementsByClassName'].includes(prop)) {
          const arg = node.arguments[0];
          if (arg && (ts.isStringLiteral(arg) || ts.isNoSubstitutionTemplateLiteral(arg))) {
            const kind = prop === 'getElementById' ? 'id' : (prop === 'getElementsByClassName' ? 'class' : 'selector');
            symbols.push(selectorSymbol(currentSource, arg.text, kind, line));
          }
          handled = true;
        }
        if (prop === 'addEventListener') {
          const eventArg = node.arguments[0];
          const cbArg = node.arguments[1];
          const eventName = eventArg && (ts.isStringLiteral(eventArg) || ts.isNoSubstitutionTemplateLiteral(eventArg)) ? eventArg.text : 'event';
          let target = `event:${eventName}`;
          let resolved = false;
          if (cbArg) {
            const ref = resolveCallbackRef(cbArg, classQName);
            if (ref) {
              target = ref;
              resolved = !ref.startsWith('event:');
            }
          }
          addRelationship({ type: 'binds_event', source: currentSource, target, line, resolved, metadata: { event: eventName } });
          handled = true;
        }
        if (['localStorage', 'sessionStorage', 'window.localStorage', 'window.sessionStorage'].includes(ownerText)) {
          const op = prop;
          const mode = ['getItem', 'key'].includes(op) ? 'read' : 'write';
          const keyArg = node.arguments[0];
          const key = keyArg && (ts.isStringLiteral(keyArg) || ts.isNoSubstitutionTemplateLiteral(keyArg)) ? keyArg.text : op;
          addRelationship({ type: mode === 'read' ? 'reads_storage' : 'writes_storage', source: currentSource, target: `storage:${ownerText}:${key}`, line, metadata: { store: ownerText, op, key } });
          handled = true;
        }
      }
      if (!handled) {
        const targetText = expr.getText(sourceFile);
        const target = resolveCallRef(expr, classQName);
        addRelationship({ type: 'calls', source: currentSource, target, line, resolved: target !== targetText });
      }
    }
    ts.forEachChild(node, child => collectRuntime(child, currentSource, classQName));
  }

  function resolveCallbackRef(node, classQName) {
    if (!node) return null;
    if (ts.isIdentifier(node)) return resolveRef(node.text, classQName);
    if (ts.isPropertyAccessExpression(node)) return resolveCallRef(node, classQName);
    if (ts.isCallExpression(node)) return resolveCallRef(node.expression, classQName);
    return null;
  }

  function resolveCallRef(expr, classQName) {
    if (ts.isIdentifier(expr)) return resolveRef(expr.text, classQName);
    if (ts.isPropertyAccessExpression(expr)) {
      if (expr.expression.kind === ts.SyntaxKind.ThisKeyword && classQName) {
        const methodName = expr.name.getText(sourceFile);
        const match = classMethods.get(classQName)?.get(methodName);
        if (match) return match;
      }
      const owner = expr.expression.getText(sourceFile);
      if (importBindings.has(owner)) {
        const info = importBindings.get(owner);
        return `${info.target}::${expr.name.getText(sourceFile)}`;
      }
      return expr.getText(sourceFile);
    }
    return expr.getText(sourceFile);
  }

  collectRuntime(sourceFile);

  symbols.sort((a, b) => (a.line - b.line) || a.name.localeCompare(b.name));
  relationships.sort((a, b) => ((a.line || 0) - (b.line || 0)) || a.type.localeCompare(b.type) || a.source.localeCompare(b.source) || a.target.localeCompare(b.target));
  imports.sort((a, b) => (a.line - b.line) || a.target.localeCompare(b.target));
  return { ok: true, language, symbols, relationships, imports, file_metadata: {} };
}

function compressJsTs(filePath, content) {
  if (!ts) throw new Error('typescript module unavailable');
  const ext = path.extname(filePath).toLowerCase();
  const sourceFile = ts.createSourceFile(filePath, content, ts.ScriptTarget.Latest, true, jsScriptKind(ext));
  const marker = markerForSuffix(ext);
  const out = [];

  function keepText(node) {
    out.push(node.getText(sourceFile).trimEnd());
    out.push('');
  }

  function signature(node, body) {
    return headerUntilBody(sourceFile, node, body);
  }

  function renderFunction(node, body) {
    const indent = '  ';
    out.push(signature(node, body));
    out.push(`${indent}// summary: ${callSummary(sourceFile, body || node)}`);
    out.push(`${indent}${marker}`);
    out.push('}');
    out.push('');
  }

  function renderClass(node) {
    const classText = node.getText(sourceFile);
    const braceIdx = classText.indexOf('{');
    out.push((braceIdx >= 0 ? classText.slice(0, braceIdx).trimEnd() + ' {' : safeTrim(classText, 220)));
    for (const member of node.members) {
      if (ts.isPropertyDeclaration(member)) {
        out.push('  ' + safeTrim(member.getText(sourceFile).trim(), 160));
        continue;
      }
      if (ts.isConstructorDeclaration(member) || ts.isMethodDeclaration(member) || ts.isGetAccessorDeclaration(member) || ts.isSetAccessorDeclaration(member)) {
        const header = signature(member, member.body);
        out.push('  ' + header.replace(/^\s+/, ''));
        out.push(`    // summary: ${callSummary(sourceFile, member.body || member)}`);
        out.push(`    ${marker}`);
        out.push('  }');
        out.push('');
      }
    }
    out.push('}');
    out.push('');
  }

  function renderObjectVariable(stmt, decl) {
    const name = decl.name.getText(sourceFile);
    const init = decl.initializer;
    const keys = [];
    for (const prop of init.properties || []) {
      if (prop.name) keys.push(safeTrim(prop.name.getText(sourceFile), 40));
      if (keys.length >= 8) break;
    }
    out.push(`${name} = {`);
    out.push(`  // summary: ${keys.length ? `keys: ${keys.join(', ')}` : 'object/config stripped'}`);
    out.push(`  ${marker}`);
    out.push('}');
    out.push('');
  }

  for (const stmt of sourceFile.statements) {
    if (ts.isImportDeclaration(stmt) || ts.isExportDeclaration(stmt) || ts.isExportAssignment(stmt)) {
      keepText(stmt);
      continue;
    }
    if (ts.isFunctionDeclaration(stmt) && stmt.body) {
      renderFunction(stmt, stmt.body);
      continue;
    }
    if (ts.isClassDeclaration(stmt)) {
      renderClass(stmt);
      continue;
    }
    if (ts.isInterfaceDeclaration(stmt) || ts.isTypeAliasDeclaration(stmt) || ts.isEnumDeclaration(stmt)) {
      keepText(stmt);
      continue;
    }
    if (ts.isVariableStatement(stmt)) {
      for (const decl of stmt.declarationList.declarations) {
        if (!ts.isIdentifier(decl.name) || !decl.initializer) continue;
        const init = decl.initializer;
        if (ts.isArrowFunction(init) || ts.isFunctionExpression(init)) {
          const text = stmt.getText(sourceFile);
          const braceIdx = text.indexOf('{');
          const header = braceIdx >= 0 ? text.slice(0, braceIdx).trimEnd() + ' {' : safeTrim(text, 160);
          out.push(header);
          out.push(`  // summary: ${callSummary(sourceFile, init.body || init)}`);
          out.push(`  ${marker}`);
          out.push('}');
          out.push('');
          continue;
        }
        if (ts.isObjectLiteralExpression(init)) {
          const text = stmt.getText(sourceFile);
          const head = text.slice(0, text.indexOf('{')).trimEnd() + ' {';
          out.push(head);
          const keys = [];
          for (const prop of init.properties || []) {
            if (prop.name) keys.push(safeTrim(prop.name.getText(sourceFile), 40));
            if (keys.length >= 8) break;
          }
          out.push(`  // summary: ${keys.length ? `keys: ${keys.join(', ')}` : 'object/config stripped'}`);
          out.push(`  ${marker}`);
          out.push('}');
          out.push('');
          continue;
        }
        if (safeTrim(stmt.getText(sourceFile), 140).length < 140) {
          keepText(stmt);
        }
      }
    }
  }
  return { ok: true, output: out.join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n' };
}

function extractHtml(projectRoot, filePath, rel, content) {
  if (!parse5) throw new Error('parse5 module unavailable');
  const doc = parse5.parse(content, { sourceCodeLocationInfo: true });
  const symbols = [];
  const relationships = [];
  const moduleNode = `module:${rel}`;
  const assets = [];
  const seenClasses = new Set();
  const seenIds = new Set();

  function addSymbol(symbol) { symbols.push(symbol); }
  function addEdge(edge) { relationships.push({ resolved: true, ...edge }); }
  function attrValue(node, name) {
    const attr = (node.attrs || []).find(a => a.name === name);
    return attr ? attr.value : null;
  }
  function lineOfNode(node) {
    return node.sourceCodeLocation?.startLine || 1;
  }
  function walk(node) {
    if (node.tagName) {
      const tag = node.tagName;
      const line = lineOfNode(node);
      addSymbol({ name: tag, type: 'html_element', line, signature: `<${tag}>`, qualified_name: `${rel}::element:${line}:${tag}`, metadata: { tag } });
      const id = attrValue(node, 'id');
      if (id && !seenIds.has(id)) {
        seenIds.add(id);
        addSymbol({ name: id, type: 'html_id', line, signature: `#${id}`, qualified_name: `${rel}::id:${id}`, metadata: { tag } });
      }
      const classes = (attrValue(node, 'class') || '').split(/\s+/).filter(Boolean);
      for (const klass of classes) {
        if (seenClasses.has(klass)) continue;
        seenClasses.add(klass);
        addSymbol({ name: klass, type: 'html_class', line, signature: `.${klass}`, qualified_name: `${rel}::class:${klass}`, metadata: { tag } });
      }
      const href = attrValue(node, 'href');
      const src = attrValue(node, 'src');
      const relAttr = attrValue(node, 'rel') || '';
      if ((tag === 'link' && href) || (tag === 'script' && src)) {
        const raw = href || src;
        const resolved = resolveProjectRelative(projectRoot, filePath, raw, ['.css', '.scss', '.sass', '.less', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx']);
        assets.push(resolved);
        addSymbol({ name: resolved, type: 'asset', line, signature: raw, qualified_name: `asset:${resolved}`, metadata: { tag, rel: relAttr || undefined, raw_path: raw } });
        addEdge({ type: 'links_asset', source: moduleNode, target: `asset:${raw}`, line, metadata: { resolved_path: resolved } });
      }
    }
    for (const child of node.childNodes || []) walk(child);
  }
  walk(doc);
  symbols.sort((a, b) => (a.line - b.line) || a.name.localeCompare(b.name));
  relationships.sort((a, b) => ((a.line || 0) - (b.line || 0)) || a.type.localeCompare(b.type) || a.target.localeCompare(b.target));
  return { ok: true, language: 'html', symbols, relationships, imports: [], file_metadata: { assets: assets.sort() } };
}

function compressHtml(filePath, content) {
  if (!parse5) throw new Error('parse5 module unavailable');
  const doc = parse5.parse(content, { sourceCodeLocationInfo: true });
  const textTags = new Set(['title', 'button', 'label', 'legend', 'option', 'textarea', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']);
  const voidTags = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']);
  const out = [];
  function renderAttrs(node) {
    const keepOrder = ['id', 'class', 'name', 'type', 'role', 'method', 'action', 'href', 'src', 'rel', 'for', 'value', 'placeholder'];
    const attrs = node.attrs || [];
    const attrMap = new Map(attrs.map(a => [a.name, a.value]));
    const kept = [];
    for (const key of keepOrder) if (attrMap.has(key) && attrMap.get(key)) kept.push(`${key}="${attrMap.get(key)}"`);
    for (const attr of attrs) if (attr.name.startsWith('data-') && attr.value) kept.push(`${attr.name}="${attr.value}"`);
    return kept.length ? ' ' + [...new Set(kept)].join(' ') : '';
  }
  function walk(node, depth = 0) {
    if (node.nodeName === '#documentType') {
      out.push('<!doctype html>');
      return;
    }
    if (node.tagName) {
      const indent = '  '.repeat(depth);
      out.push(`${indent}<${node.tagName}${renderAttrs(node)}${voidTags.has(node.tagName) ? ' />' : '>'}`);
      if (['script', 'style'].includes(node.tagName)) {
        out.push(`${indent}  <!-- inline content stripped by Qompressor -->`);
      }
      for (const child of node.childNodes || []) {
        if (child.nodeName === '#text') {
          const text = safeTrim(child.value || '', 80);
          if (text && textTags.has(node.tagName)) out.push(`${indent}  ${text}`);
        } else {
          walk(child, depth + 1);
        }
      }
      if (!voidTags.has(node.tagName)) out.push(`${indent}</${node.tagName}>`);
      return;
    }
    for (const child of node.childNodes || []) walk(child, depth);
  }
  walk(doc, 0);
  return { ok: true, output: out.join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n' };
}

function extractCss(projectRoot, filePath, rel, content) {
  if (!postcss) throw new Error('postcss module unavailable');
  const root = postcss.parse(content, { from: filePath });
  const symbols = [];
  const relationships = [];
  const imports = [];
  const mediaQueries = [];
  const moduleNode = `module:${rel}`;
  let selectorIndex = 0;

  root.walkAtRules((rule) => {
    if (rule.name === 'import') {
      const match = /["']([^"']+)["']/.exec(rule.params || '');
      if (match) {
        const target = resolveProjectRelative(projectRoot, filePath, match[1], ['.css', '.scss', '.sass', '.less']);
        imports.push({ target, line: rule.source?.start?.line || 1 });
        relationships.push({ type: 'imports', source: moduleNode, target, line: rule.source?.start?.line || 1, resolved: true });
      }
    } else if (rule.name === 'media') {
      mediaQueries.push(rule.params);
    }
  });

  root.walkRules((rule) => {
    const line = rule.source?.start?.line || 1;
    for (const rawSelector of String(rule.selector || '').split(',')) {
      const selectorValue = rawSelector.trim();
      if (!selectorValue) continue;
      selectorIndex += 1;
      symbols.push({
        name: selectorValue,
        type: 'selector',
        line,
        signature: selectorValue,
        qualified_name: `${rel}::selector:${line}:${selectorIndex}`,
        metadata: { selector_value: selectorValue, simple_tokens: simpleSelectorTokens(selectorValue) },
      });
    }
  });

  const customProperties = [];
  root.walkDecls((decl) => {
    if (decl.prop && decl.prop.startsWith('--')) customProperties.push(decl.prop);
  });

  symbols.sort((a, b) => (a.line - b.line) || a.name.localeCompare(b.name));
  relationships.sort((a, b) => ((a.line || 0) - (b.line || 0)) || a.type.localeCompare(b.type) || a.target.localeCompare(b.target));
  return { ok: true, language: 'css', symbols, relationships, imports, file_metadata: { media_queries: mediaQueries, custom_properties: [...new Set(customProperties)] } };
}

function compressCss(filePath, content) {
  if (!postcss) throw new Error('postcss module unavailable');
  const root = postcss.parse(content, { from: filePath });
  const marker = markerForSuffix(path.extname(filePath).toLowerCase());
  const out = [];
  const important = new Set(['display', 'position', 'grid-template-columns', 'grid-template-areas', 'grid-area', 'flex', 'flex-direction', 'gap', 'width', 'height', 'min-height', 'max-width', 'font', 'font-size', 'font-weight', 'color', 'background', 'background-color', 'animation', 'transition']);

  root.each((node) => {
    if (node.type === 'atrule' && node.name === 'import') {
      out.push(node.toString());
      out.push('');
      return;
    }
    if (node.type === 'atrule' && node.name === 'media') {
      out.push(`@media ${node.params} {`);
      node.each((child) => {
        if (child.type !== 'rule') return;
        out.push(`  ${child.selector} {`);
        child.walkDecls((decl) => {
          if (decl.prop.startsWith('--') || important.has(decl.prop)) out.push(`    ${decl.prop}: ${safeTrim(decl.value, 70)};`);
        });
        out.push(`    ${marker}`);
        out.push('  }');
        out.push('');
      });
      out.push('}');
      out.push('');
      return;
    }
    if (node.type === 'rule') {
      out.push(`${node.selector} {`);
      node.walkDecls((decl) => {
        if (decl.prop.startsWith('--') || important.has(decl.prop)) out.push(`  ${decl.prop}: ${safeTrim(decl.value, 70)};`);
      });
      out.push(`  ${marker}`);
      out.push('}');
      out.push('');
    }
  });
  return { ok: true, output: out.join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n' };
}

function capabilities() {
  printJson({
    available: true,
    node: process.version,
    typescript: !!ts,
    typescript_version: ts && ts.version,
    postcss: !!postcss,
    parse5: !!parse5,
  });
}

function main() {
  const command = process.argv[2];
  try {
    if (command === 'capabilities') return capabilities();
    const args = process.argv.slice(3);
    const content = readStdin();
    if (command === 'extract-js-ts') {
      const [projectRoot, filePath, rel] = args;
      return printJson(extractJsTs(projectRoot, filePath, rel, content));
    }
    if (command === 'compress-js-ts') {
      const [filePath] = args;
      return printJson(compressJsTs(filePath, content));
    }
    if (command === 'extract-html') {
      const [projectRoot, filePath, rel] = args;
      return printJson(extractHtml(projectRoot, filePath, rel, content));
    }
    if (command === 'compress-html') {
      const [filePath] = args;
      return printJson(compressHtml(filePath, content));
    }
    if (command === 'extract-css') {
      const [projectRoot, filePath, rel] = args;
      return printJson(extractCss(projectRoot, filePath, rel, content));
    }
    if (command === 'compress-css') {
      const [filePath] = args;
      return printJson(compressCss(filePath, content));
    }
    throw new Error(`unknown command: ${command}`);
  } catch (err) {
    process.stderr.write((err && err.stack) ? err.stack : String(err));
    process.exit(1);
  }
}

main();
