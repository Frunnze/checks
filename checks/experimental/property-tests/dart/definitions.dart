import 'package:analyzer/dart/ast/ast.dart';
import 'package:analyzer/dart/ast/token.dart';
import 'package:analyzer/dart/ast/visitor.dart';

const Set<String> objectProtocolNames = {
  'toString',
  'hashCode',
  'noSuchMethod',
};
const String widgetTypeName = 'Widget';
const String overrideAnnotationName = 'override';

final class Definition {
  const Definition({
    required this.name,
    required this.offset,
    required this.isOverride,
  });

  final String name;
  final int offset;
  final bool isOverride;
}

bool isMarkedOverride(NodeList<Annotation> metadata) {
  return metadata.any(
    (annotation) => annotation.name.name == overrideAnnotationName,
  );
}

final class DefinitionCollector extends RecursiveAstVisitor<void> {
  final List<Definition> definitions = [];

  @override
  void visitFunctionDeclaration(FunctionDeclaration node) {
    _collect(
      node.name,
      node.returnType,
      node.functionExpression.body,
      isOverride: false,
    );
    super.visitFunctionDeclaration(node);
  }

  @override
  void visitMethodDeclaration(MethodDeclaration node) {
    if (!node.isOperator) {
      _collect(
        node.name,
        node.returnType,
        node.body,
        isOverride: isMarkedOverride(node.metadata),
      );
    }

    super.visitMethodDeclaration(node);
  }

  void _collect(
    Token name,
    TypeAnnotation? returnType,
    FunctionBody body, {
    required bool isOverride,
  }) {
    final isObjectProtocol = objectProtocolNames.contains(name.lexeme);

    if (isObjectProtocol || _hasNoBody(body) || _buildsWidget(returnType)) {
      return;
    }

    definitions.add(
      Definition(
        name: name.lexeme,
        offset: name.offset,
        isOverride: isOverride,
      ),
    );
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

final class DeclaredNameCollector extends RecursiveAstVisitor<void> {
  final Set<String> declaredNames = {};

  @override
  void visitFunctionDeclaration(FunctionDeclaration node) {
    declaredNames.add(node.name.lexeme);
    super.visitFunctionDeclaration(node);
  }

  @override
  void visitMethodDeclaration(MethodDeclaration node) {
    if (!isMarkedOverride(node.metadata)) {
      declaredNames.add(node.name.lexeme);
    }

    super.visitMethodDeclaration(node);
  }

  @override
  void visitFieldDeclaration(FieldDeclaration node) {
    _addVariables(node.fields);
    super.visitFieldDeclaration(node);
  }

  @override
  void visitTopLevelVariableDeclaration(TopLevelVariableDeclaration node) {
    _addVariables(node.variables);
    super.visitTopLevelVariableDeclaration(node);
  }

  void _addVariables(VariableDeclarationList declarations) {
    for (final variable in declarations.variables) {
      declaredNames.add(variable.name.lexeme);
    }
  }
}

List<Definition> definitionsIn(CompilationUnit unit) {
  final collector = DefinitionCollector();
  unit.accept(collector);

  return collector.definitions;
}

Set<String> declaredNamesIn(CompilationUnit unit) {
  final collector = DeclaredNameCollector();
  unit.accept(collector);

  return collector.declaredNames;
}

bool overridesLibraryMember(Definition definition, Set<String> ownNames) {
  return definition.isOverride && !ownNames.contains(definition.name);
}
