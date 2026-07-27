import { StyleSheet, Text, View } from "react-native";

import { AppScreen } from "@/components/app-screen";
import { InfoCard } from "@/components/info-card";
import { colors, spacing, type } from "@/theme/tokens";

export default function CoachTeamScreen() {
  return (
    <AppScreen>
      <View style={styles.heading}>
        <Text style={styles.eyebrow}>สำหรับโค้ช</Text>
        <Text style={styles.title}>ภาพรวมทีม</Text>
        <Text style={styles.subtitle}>หน้าพรีวิวนี้ไม่มีข้อมูลทีมจริง</Text>
      </View>

      <InfoCard
        label="ทีม"
        title="ยังไม่มีนักกีฬาในพื้นที่พรีวิว"
        description="เมื่อระบบสมาชิกพร้อม คุณจะเห็นเฉพาะนักกีฬาที่อยู่ในทีมและยินยอมแชร์ข้อมูล"
        accent="primary"
      />
      <InfoCard
        label="ธงเฝ้าระวัง"
        title="ไม่มีข้อมูลให้ประเมิน"
        description="ธงจะอธิบายเหตุผลอย่างชัดเจนและใช้ช่วยตัดสินใจ ไม่ใช่การวินิจฉัย"
      />
      <InfoCard
        label="แผนซ้อม"
        title="การสร้างแผนยังไม่เปิดใช้งาน"
        description="ฟังก์ชันสร้างและเผยแพร่แผนจะเพิ่มหลังระบบสิทธิ์และทีมผ่านการทดสอบ"
      />
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  heading: {
    gap: spacing.xs,
    marginBottom: spacing.md,
  },
  eyebrow: {
    color: colors.primaryStrong,
    fontSize: type.caption,
    fontWeight: "800",
    letterSpacing: 1,
  },
  title: {
    color: colors.ink,
    fontSize: type.title,
    fontWeight: "800",
  },
  subtitle: {
    color: colors.inkMuted,
    fontSize: type.small,
    lineHeight: 20,
  },
});
