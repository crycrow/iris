<script setup>
import { useRoute } from "vue-router";
import UiIcon from "./UiIcon.vue";
import { severities } from "../utils/format.js";
const route = useRoute();
defineProps({ risks: { type: Array, default: () => [] } });
</script>
<template>
  <span v-if="risks.length" class="risk-badges"
    ><RouterLink
      v-for="risk in risks"
      :key="risk.risk_id"
      :to="{
        path: `/risks/${risk.risk_id}`,
        query: { returnTo: route?.fullPath || '/' },
      }"
      @click.stop
      @keydown.stop
      class="risk-marker"
      :class="[risk.severity, { 'cause-resolved': risk.is_cause_resolved }]"
      :title="`${risk.is_cause_resolved ? 'Основание устранено. ' : ''}${severities[risk.severity] || ''} критичность. ${risk.description || risk.type_name || ''}`"
      :aria-label="`Риск ${risk.type_name || risk.name || 'без названия'}. ${risk.is_cause_resolved ? 'Основание устранено. ' : ''}${severities[risk.severity] || 'Неизвестная'} критичность. ${risk.description || ''}`"
      ><UiIcon :name="risk.is_cause_resolved ? 'check' : 'risk'" />
      {{ risk.type_name || risk.name || "Риск" }}</RouterLink
    ></span
  >
</template>

<style scoped>
.risk-marker > svg {
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
  vertical-align: middle;
}
</style>
