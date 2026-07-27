import { useRouter } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { AppScreen } from "@/components/app-screen";
import { RoleCard } from "@/components/role-card";
import { roleOptions } from "@/features/role-preview/role-options";
import { colors, radius, spacing, type } from "@/theme/tokens";

export default function RolePreviewScreen() {
  const router = useRouter();

  return (
    <AppScreen>
      <View style={styles.brand}>
        <View style={styles.mark} />
        <Text style={styles.eyebrow}>RUN PERFORMANCE</Text>
      </View>

      <View style={styles.hero}>
        <Text style={styles.title}>วันนี้ เริ่มจากสิ่งที่สำคัญ</Text>
        <Text style={styles.description}>
          ดูแผนซ้อม ส่งความรู้สึกหลังวิ่ง และช่วยให้โค้ชดูแลทีมได้ทันเวลา
        </Text>
      </View>

      <View style={styles.previewNotice}>
        <Text style={styles.previewTitle}>โหมดพรีวิวสำหรับการพัฒนา</Text>
        <Text style={styles.previewText}>
          หน้านี้จะถูกแทนด้วยการเข้าสู่ระบบและบทบาทจากเซิร์ฟเวอร์ในภายหลัง
        </Text>
      </View>

      <View style={styles.roles}>
        {roleOptions.map((role) => (
          <RoleCard
            key={role.id}
            title={role.title}
            description={role.description}
            actionLabel={role.actionLabel}
            primary={role.id === "athlete"}
            onPress={() => router.push(role.route)}
          />
        ))}
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  brand: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  mark: {
    width: 12,
    height: 12,
    borderRadius: radius.full,
    backgroundColor: colors.primary,
  },
  eyebrow: {
    color: colors.primaryStrong,
    fontSize: type.caption,
    fontWeight: "800",
    letterSpacing: 1.5,
  },
  hero: {
    gap: spacing.md,
    marginTop: spacing.xxl,
  },
  title: {
    color: colors.ink,
    fontSize: type.display,
    fontWeight: "800",
    lineHeight: 44,
    maxWidth: 520,
  },
  description: {
    color: colors.inkMuted,
    fontSize: type.body,
    lineHeight: 25,
    maxWidth: 560,
  },
  previewNotice: {
    backgroundColor: colors.notice,
    borderRadius: radius.md,
    gap: spacing.xs,
    marginTop: spacing.xl,
    padding: spacing.lg,
  },
  previewTitle: {
    color: colors.noticeInk,
    fontSize: type.label,
    fontWeight: "700",
  },
  previewText: {
    color: colors.noticeInk,
    fontSize: type.small,
    lineHeight: 20,
  },
  roles: {
    gap: spacing.md,
    marginTop: spacing.lg,
  },
});
