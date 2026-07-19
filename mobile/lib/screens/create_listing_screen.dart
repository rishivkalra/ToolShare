import 'package:flutter/material.dart';

import '../api/client.dart';
import 'browse_screen.dart' show currentPosition;

const _categories = [
  'power_tools',
  'hand_tools',
  'garden',
  'ladders_access',
  'painting_decorating',
  'plumbing',
  'automotive',
  'cleaning',
  'measuring',
  'other',
];

class CreateListingScreen extends StatefulWidget {
  const CreateListingScreen({super.key});

  @override
  State<CreateListingScreen> createState() => _CreateListingScreenState();
}

class _CreateListingScreenState extends State<CreateListingScreen> {
  final _title = TextEditingController();
  final _description = TextEditingController();
  final _price = TextEditingController(text: '8');
  final _deposit = TextEditingController(text: '50');
  final _address = TextEditingController();
  String _category = 'power_tools';
  bool _busy = false;

  Future<void> _submit() async {
    setState(() => _busy = true);
    try {
      final pos = await currentPosition();
      await ApiClient.instance.createListing({
        'title': _title.text.trim(),
        'description': _description.text.trim(),
        'category': _category,
        'price_per_day_cents':
            ((double.tryParse(_price.text) ?? 0) * 100).round(),
        'deposit_cents': ((double.tryParse(_deposit.text) ?? 0) * 100).round(),
        'lat': pos.latitude,
        'lng': pos.longitude,
        'exact_address': _address.text.trim(),
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Listed! Your tool is now visible to neighbors.')));
      _title.clear();
      _description.clear();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Could not list: $e')));
    } finally {
      setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('List a tool')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _title,
            decoration: const InputDecoration(
              labelText: 'What are you lending?',
              hintText: 'e.g. DeWalt circular saw',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            initialValue: _category,
            decoration: const InputDecoration(
                labelText: 'Category', border: OutlineInputBorder()),
            items: [
              for (final c in _categories)
                DropdownMenuItem(
                    value: c, child: Text(c.replaceAll('_', ' '))),
            ],
            onChanged: (v) => setState(() => _category = v ?? _category),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _description,
            maxLines: 3,
            decoration: const InputDecoration(
              labelText: 'Description (optional)',
              hintText: 'Condition notes, blade size, battery included…',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _price,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                      labelText: 'Price per day (\$)',
                      border: OutlineInputBorder()),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: _deposit,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                      labelText: 'Deposit (\$, 0 = none)',
                      border: OutlineInputBorder()),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _address,
            decoration: const InputDecoration(
              labelText: 'Pickup address',
              helperText: 'Only shared after a confirmed booking',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy ? null : _submit,
            child: Text(_busy ? 'Listing…' : 'List my tool'),
          ),
          const SizedBox(height: 8),
          const Text(
            'You keep 100% of your listed price — the borrower pays the '
            'service fee. Payouts arrive via Stripe after each rental.',
            style: TextStyle(fontSize: 12, color: Colors.grey),
          ),
        ],
      ),
    );
  }
}
