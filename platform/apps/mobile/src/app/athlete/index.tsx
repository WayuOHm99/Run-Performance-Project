import { StyleSheet, Text, View } from "react-native";

import { AppScreen } from "@/components/app-screen";
import { InfoCard } from "@/components/info-card";
import { colors, spacing, type } from "@/theme/tokens";

export default function AthleteTodayScreen() {
  return (
    <AppScreen>
      <View style={styles.heading}>
        <Text style={styles.eyebrow}>สำหรับนักกีฬา</Text>
        <Text style={styles.title}>แผนของวันนี้</Text>
        <Text style={styles.subtitle}>
          พื้นที่นี้ใช้ข้อมูลตัวอย่างและยังไม่เชื่อมบัญชีจริง
        </Text>
      </View>

      <InfoCard
        label="การซ้อม"
        title="ยังไม่มีแผนที่เผยแพร่"
        description="เมื่อโค้ชส่งแผน รายละเอียดการซ้อมวันนี้จะปรากฏตรงนี้"
        accent="primary"
      />
      <InfoCard
        label="การนอน"
        title="ยังไม่ได้เชื่อมต่อ"
        description="ข้อมูลการนอนจะต้องได้รับอนุญาตจากคุณก่อนนำมาแสดงหรือแชร์"
      />
      <InfoCard
        label="เช็กอิน"
        title="ยังไม่เปิดใช้งานในขั้นนี้"
        description="ขั้นถัดไปจะเพิ่ม RPE ความรู้สึก และการรายงานอาการเจ็บแบบสั้น"
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
