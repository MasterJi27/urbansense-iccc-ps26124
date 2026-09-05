import 'package:flutter_test/flutter_test.dart';
import 'package:urbansense_mobile/main.dart';

void main() {
  testWidgets('login screen renders', (tester) async {
    await tester.pumpWidget(const SadakSaarthiApp());
    expect(find.text('SADAKSAARTHI'), findsOneWidget);
    expect(find.text('Login'), findsOneWidget);
  });
}
