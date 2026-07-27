import { useRouter } from "expo-router";
import { StyleSheet, View } from "react-native";

import { AppScreen } from "@/components/app-screen";
import { PrimaryButton } from "@/components/primary-button";
import { RoleCard } from "@/components/role-card";
import { ScreenHeading } from "@/components/screen-heading";
import { useAuth } from "@/features/auth/auth-provider";
import { roleRoute, type AppRole } from "@/features/auth/gate";
import { useAuthGate } from "@/features/profile/use-account";
import { spacing } from "@/theme/tokens";

const ROLE_COPY: Record<AppRole, { title: string; description: string }> = {
  athlete: {
    title: "นักกีฬา",
    description: "ดูแผนซ้อมวันนี้และส่งข้อมูลหลังซ้อม",
  },
  coach: {
    title: "โค้ช",
    description: "ดูภาพรวมทีมและจัดการแผนซ้อม",
  },
};

/**
 * The role chooser for a genuinely dual-role user.
 *
 * The list is built from `gate.authorizedRoles`, which comes only from active
 * membership rows. A role the database did not return cannot appear here, so
 * the chooser can never offer more than the backend would allow.
 *
 * The choice is navigation, not authorization. It is not written to storage, a
 * JWT claim, or user metadata, and it does not widen any query: entering the
 * coach shell still returns only what an active coach membership permits.
 */
export default function ChooseRoleScreen() {
  const gate = useAuthGate();
  const router = useRouter();
  const { signOut } = useAuth();

  const roles = gate.status === "ready" ? gate.authorizedRoles : [];

  return (
    <AppScreen>
      <ScreenHeading
        title="เลือกพื้นที่ที่ต้องการใช้งาน"
        description="คุณมีบทบาทที่ใช้งานอยู่มากกว่าหนึ่งบทบาท"
      />

      <View style={styles.roles}>
        {roles.map((role) => (
          <RoleCard
            key={role}
            title={ROLE_COPY[role].title}
            description={ROLE_COPY[role].description}
            actionLabel="เข้าใช้งาน"
            primary={role === "athlete"}
            onPress={() => {
              router.push(roleRoute(role));
            }}
          />
        ))}

        <PrimaryButton
          label="ออกจากระบบ"
          variant="quiet"
          onPress={() => {
            void signOut();
          }}
        />
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  roles: {
    gap: spacing.md,
    marginTop: spacing.lg,
  },
});
