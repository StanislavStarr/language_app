import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';

import { useTheme } from '@/shared/ui';

type IconName = 'library-outline' | 'book-outline' | 'person-outline';

type TabBarIconProps = {
  name: IconName;
  focused: boolean;
  size: number;
};

function TabBarIcon({ name, focused, size }: TabBarIconProps) {
  const { colors } = useTheme();

  return <Ionicons name={name} size={size} color={focused ? colors.primary : colors.textMuted} />;
}

function tabIcon(name: IconName) {
  return function renderTabIcon({ focused, size }: { focused: boolean; size: number }) {
    return <TabBarIcon name={name} focused={focused} size={size} />;
  };
}

export function TabsLayout() {
  const { colors } = useTheme();

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarStyle: { backgroundColor: colors.background, borderTopColor: colors.border },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: 'Библиотека', tabBarIcon: tabIcon('library-outline') }}
      />
      <Tabs.Screen
        name="vocabulary"
        options={{ title: 'Словарь', tabBarIcon: tabIcon('book-outline') }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: 'Профиль', tabBarIcon: tabIcon('person-outline') }}
      />
    </Tabs>
  );
}
