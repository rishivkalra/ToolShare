import 'package:flutter/material.dart';

import '../api/client.dart';

class BookingDetailScreen extends StatefulWidget {
  const BookingDetailScreen({super.key, required this.bookingId});

  final String bookingId;

  @override
  State<BookingDetailScreen> createState() => _BookingDetailScreenState();
}

class _BookingDetailScreenState extends State<BookingDetailScreen> {
  Booking? _booking;
  List<Message> _messages = [];
  String _me = '';
  final _draft = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = ApiClient.instance;
    final booking = await api.booking(widget.bookingId);
    final messages = await api.messages(widget.bookingId);
    final me = await api.me();
    if (!mounted) return;
    setState(() {
      _booking = booking;
      _messages = messages;
      _me = me.uid;
    });
  }

  Future<void> _act(String action) async {
    try {
      final updated =
          await ApiClient.instance.bookingAction(widget.bookingId, action);
      setState(() => _booking = updated);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Action failed: $e')));
    }
  }

  Future<void> _review() async {
    try {
      await ApiClient.instance.leaveReview(widget.bookingId, 5, '');
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Thanks for the review!')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Review failed: $e')));
    }
  }

  Future<void> _send() async {
    final text = _draft.text.trim();
    if (text.isEmpty) return;
    await ApiClient.instance.sendMessage(widget.bookingId, text);
    _draft.clear();
    final messages = await ApiClient.instance.messages(widget.bookingId);
    setState(() => _messages = messages);
  }

  List<Widget> _actions(Booking b) {
    final isLender = _me == b.lenderUid;
    final actions = <Widget>[];
    void add(String label, String action) => actions.add(Padding(
          padding: const EdgeInsets.only(top: 8),
          child: FilledButton(
              onPressed: () => _act(action), child: Text(label)),
        ));

    if (b.state == 'requested' && isLender) {
      add('Approve & charge borrower', 'approve');
      add('Decline', 'decline');
    }
    if (b.state == 'confirmed') {
      final mine = isLender ? b.lenderMarkedPickup : b.borrowerMarkedPickup;
      if (!mine) add('Confirm handoff (pickup)', 'pickup');
      add('Cancel booking', 'cancel');
    }
    if (b.state == 'picked_up' && isLender) {
      add('Tool returned — all good', 'return');
    }
    if (b.state == 'completed') {
      actions.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: OutlinedButton(
            onPressed: _review, child: const Text('Leave a 5★ review')),
      ));
    }
    return actions;
  }

  @override
  Widget build(BuildContext context) {
    final b = _booking;
    if (b == null) {
      return Scaffold(
          appBar: AppBar(),
          body: const Center(child: CircularProgressIndicator()));
    }
    return Scaffold(
      appBar: AppBar(title: Text(b.listingTitle)),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${b.startDate} → ${b.endDate} · ${dollars(b.totalCents)} '
                    '· ${b.state.replaceAll('_', ' ')}'),
                if (b.exactAddress.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text('Pickup: ${b.exactAddress}',
                        style: const TextStyle(fontWeight: FontWeight.w600)),
                  ),
                ..._actions(b),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: _messages.length,
              itemBuilder: (context, i) {
                final m = _messages[i];
                final mine = m.senderUid == _me;
                return Align(
                  alignment:
                      mine ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    margin: const EdgeInsets.symmetric(vertical: 3),
                    padding: const EdgeInsets.all(10),
                    constraints: BoxConstraints(
                        maxWidth: MediaQuery.of(context).size.width * 0.75),
                    decoration: BoxDecoration(
                      color: mine
                          ? Theme.of(context).colorScheme.primaryContainer
                          : Theme.of(context)
                              .colorScheme
                              .surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(m.text),
                  ),
                );
              },
            ),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _draft,
                      decoration: const InputDecoration(
                        hintText: 'Message your neighbor…',
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                      onSubmitted: (_) => _send(),
                    ),
                  ),
                  IconButton(onPressed: _send, icon: const Icon(Icons.send)),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
