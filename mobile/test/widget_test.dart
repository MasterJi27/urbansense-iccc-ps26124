import 'package:flutter_test/flutter_test.dart';
import 'package:urbansense_mobile/main.dart';

void main() {
  testWidgets('login screen renders', (tester) async {
    await tester.pumpWidget(const UrbanSenseApp());
    expect(find.text('URBANSENSE'), findsOneWidget);
    expect(find.text('Login'), findsOneWidget);
  });
}
