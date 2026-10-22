import 'package:analyzer/dart/ast/ast.dart';
import 'package:analyzer/dart/ast/visitor.dart';

const String kiriCheckLibrary = 'package:kiri_check/';
const String propertyFunctionName = 'property';

final class KiriCheckImports {
  const KiriCheckImports({required this.isUnprefixed, required this.prefixes});

  final bool isUnprefixed;
  final Set<String> prefixes;

  bool allowsTarget(Expression? target) {
    if (target == null) {
      return isUnprefixed;
    }

    return target is SimpleIdentifier && prefixes.contains(target.name);
  }
}

KiriCheckImports kiriCheckImportsIn(CompilationUnit unit) {
  var isUnprefixed = false;
  final prefixes = <String>{};

  for (final directive in unit.directives.whereType<ImportDirective>()) {
    final importedUri = directive.uri.stringValue ?? '';

    if (!importedUri.startsWith(kiriCheckLibrary)) {
      continue;
    }

    final prefix = directive.prefix;

    if (prefix == null) {
      isUnprefixed = true;
    } else {
      prefixes.add(prefix.name);
    }
  }

  return KiriCheckImports(isUnprefixed: isUnprefixed, prefixes: prefixes);
}

final class PropertyTitleCollector extends RecursiveAstVisitor<void> {
  PropertyTitleCollector(this.kiriCheckImports);

  final KiriCheckImports kiriCheckImports;
  final Set<String> titles = {};

  @override
  void visitMethodInvocation(MethodInvocation node) {
    final title = _propertyTitleOf(node);

    if (title != null) {
      titles.add(title);
    }

    super.visitMethodInvocation(node);
  }

  String? _propertyTitleOf(MethodInvocation node) {
    if (node.methodName.name != propertyFunctionName) {
      return null;
    }

    if (!kiriCheckImports.allowsTarget(node.target)) {
      return null;
    }

    final arguments = node.argumentList.arguments;

    if (arguments.isEmpty) {
      return null;
    }

    final firstArgument = arguments.first;

    if (firstArgument is! StringLiteral) {
      return null;
    }

    return firstArgument.stringValue;
  }
}

Set<String> propertyTestTitlesIn(CompilationUnit unit) {
  final collector = PropertyTitleCollector(kiriCheckImportsIn(unit));
  unit.accept(collector);

  return collector.titles;
}
