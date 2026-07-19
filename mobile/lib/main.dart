import 'package:flutter/material.dart';

import 'api/client.dart';
import 'screens/bookings_screen.dart';
import 'screens/browse_screen.dart';
import 'screens/create_listing_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/project_kit_screen.dart';

void main() {
  // Dev sign-in; production replaces this with a Firebase ID token after
  // Sign in with Apple / Google / phone OTP.
  ApiClient.instance.setToken('dev:demo');
  runApp(const ToolShareApp());
}

class ToolShareApp extends StatelessWidget {
  const ToolShareApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ToolShare',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2F6D3A)),
        useMaterial3: true,
      ),
      home: const HomeShell(),
    );
  }
}

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _screens = [
    BrowseScreen(),
    ProjectKitScreen(),
    CreateListingScreen(),
    BookingsScreen(),
    ProfileScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _screens[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.search), label: 'Browse'),
          NavigationDestination(icon: Icon(Icons.auto_awesome), label: 'Project'),
          NavigationDestination(icon: Icon(Icons.add_circle_outline), label: 'List'),
          NavigationDestination(icon: Icon(Icons.handshake_outlined), label: 'Rentals'),
          NavigationDestination(icon: Icon(Icons.person_outline), label: 'Profile'),
        ],
      ),
    );
  }
}
