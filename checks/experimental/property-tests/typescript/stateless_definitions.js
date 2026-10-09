const ELEMENT_RETURN_TYPE = "JSX.Element";
const CONSTRUCTOR_NAME = "constructor";

function isCapitalised(name) {
  return name.length > 0 && name[0] === name[0].toUpperCase();
}

function returnsAnElement(node) {
  return node.type !== undefined && node.type.getText() === ELEMENT_RETURN_TYPE;
}

function hasNoBody(node) {
  return node.body === undefined;
}

function hasEmptyBody(typescript, node) {
  return (
    node.body !== undefined &&
    typescript.isBlock(node.body) &&
    node.body.statements.length === 0
  );
}

function describesNoBehaviour(typescript, definition) {
  if (definition.name === CONSTRUCTOR_NAME) return true;
  if (hasNoBody(definition.node)) return true;
  if (hasEmptyBody(typescript, definition.node)) return true;

  return isCapitalised(definition.name) && returnsAnElement(definition.node);
}

module.exports = { describesNoBehaviour };
