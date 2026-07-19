import 'package:flutter/material.dart';

import '../api/client.dart';
import 'browse_screen.dart' show currentPosition;
import 'listing_detail_screen.dart';

/// The differentiator screen: describe a project, get the tool list matched
/// against what neighbors actually have, rent the whole kit.
class ProjectKitScreen extends StatefulWidget {
  const ProjectKitScreen({super.key});

  @override
  State<ProjectKitScreen> createState() => _ProjectKitScreenState();
}

class _ProjectKitScreenState extends State<ProjectKitScreen> {
  final _controller = TextEditingController();
  ProjectKit? _kit;
  bool _loading = false;
  String _error = '';

  Future<void> _plan() async {
    final description = _controller.text.trim();
    if (description.length < 10) {
      setState(() => _error = 'Describe your project in a sentence or two.');
      return;
    }
    setState(() {
      _loading = true;
      _error = '';
      _kit = null;
    });
    try {
      final pos = await currentPosition();
      final kit = await ApiClient.instance
          .planProject(description, pos.latitude, pos.longitude);
      setState(() => _kit = kit);
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final kit = _kit;
    return Scaffold(
      appBar: AppBar(title: const Text('Plan a project')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text(
            "Tell us what you're building — we'll figure out the tools and "
            'find them in your neighborhood.',
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _controller,
            maxLines: 3,
            decoration: const InputDecoration(
              hintText: 'e.g. I want to build a raised garden bed in my backyard',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: _loading ? null : _plan,
            icon: const Icon(Icons.auto_awesome),
            label: Text(_loading ? 'Planning…' : 'Build my tool kit'),
          ),
          if (_error.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_error, style: const TextStyle(color: Colors.red)),
            ),
          if (kit != null) ...[
            const SizedBox(height: 20),
            Text(kit.projectSummary,
                style: Theme.of(context).textTheme.titleMedium),
            if (kit.totalEstimatedPerDayCents > 0)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  'Rent the kit from '
                  '${dollars(kit.totalEstimatedPerDayCents)}/day '
                  '— instead of buying it all.',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              ),
            const SizedBox(height: 8),
            for (final item in kit.kit) _KitTile(item: item),
            if (kit.missingTools.isNotEmpty)
              Card(
                color: Theme.of(context).colorScheme.surfaceContainerHighest,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(
                    'Not yet available nearby: ${kit.missingTools.join(', ')}. '
                    "We'll notify you when a neighbor lists one.",
                  ),
                ),
              ),
            if (kit.consumablesNote.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(kit.consumablesNote,
                    style: const TextStyle(color: Colors.grey)),
              ),
            if (kit.safetyNote.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('⚠️ ${kit.safetyNote}',
                    style: const TextStyle(color: Colors.grey)),
              ),
          ],
        ],
      ),
    );
  }
}

class _KitTile extends StatelessWidget {
  const _KitTile({required this.item});

  final KitItem item;

  @override
  Widget build(BuildContext context) {
    final best = item.matches.isNotEmpty ? item.matches.first : null;
    return Card(
      child: ListTile(
        leading: Icon(
          best != null ? Icons.check_circle_outline : Icons.hourglass_empty,
          color: best != null ? Colors.green : Colors.grey,
        ),
        title: Text(
          item.tool.name + (item.tool.optional ? ' (optional)' : ''),
        ),
        subtitle: Text(
          best != null
              ? '${best.title} · ${dollars(best.pricePerDayCents)}/day'
              : item.tool.why,
        ),
        trailing: best != null ? const Icon(Icons.chevron_right) : null,
        onTap: best != null
            ? () => Navigator.push(
                  context,
                  MaterialPageRoute(
                      builder: (_) => ListingDetailScreen(listingId: best.id)),
                )
            : null,
      ),
    );
  }
}
