import 'package:analyzer/dart/ast/ast.dart';
import 'package:analyzer/dart/ast/token.dart';
import 'package:analyzer/dart/ast/visitor.dart';

const Set<String> objectProtocolNames = {
  'toString',
  'hashCode',
  'noSuchMethod',
};
const String widgetTypeName = 'Widget';

final class Definition {
  const Definition({required this.name, required this.offset});

  final String name;
  final int offset;
}

final class DefinitionCollector extends RecursiveAstVisitor<void> {
  final List<Definition> definitions = [];

  @override
  void visitFunctionDeclaration(FunctionDeclaration node) {
    _collect(node.name, node.returnType, node.functionExpression.body);
    super.visitFunctionDeclaration(node);
  }

  @override
  void visitMethodDeclaration(MethodDeclaration node) {
    if (!node.isOperator) {
      _collect(node.name, node.returnType, node.body);
    }

    super.visitMethodDeclaration(node);
  }

  void _collect(Token name, TypeAnnotation? returnType, FunctionBody body) {
    final isObjectProtocol = objectProtocolNames.contains(name.lexeme);

    if (isObjectProtocol || _hasNoBody(body) || _buildsWidget(returnType)) {
      return;
    }

    definitions.add(Definition(name: name.lexeme, offset: name.offset));
  }

  bool _hasNoBody(FunctionBody body) {
    if (body is EmptyFunctionBody) {
      return true;
    }

    return body is BlockFunctionBody && body.block.statements.isEmpty;
  }

  bool _buildsWidget(TypeAnnotation? returnType) {
    return returnType is NamedType && returnType.name.lexeme == widgetTypeName;
  }
}

List<Definition> definitionsIn(CompilationUnit unit) {
  final collector = DefinitionCollector();
  unit.accept(collector);

  return collector.definitions;
}
