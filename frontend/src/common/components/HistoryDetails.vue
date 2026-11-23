<script setup>
defineProps({ details: { type: Array, default: () => [] } });
</script>

<template>
  <dl v-if="details.length" class="history-details">
    <div v-for="(detail, index) in details" :key="index">
      <dt v-if="detail.label">{{ detail.label }}</dt>
      <dd :class="{ 'full-width': !detail.label }">{{ detail.value }}</dd>
    </div>
  </dl>
</template>

<style scoped>
.history-details { margin: 8px 0 0; }
.history-details > div { display: grid; grid-template-columns: minmax(120px, 32%) minmax(0, 1fr); gap: 4px 16px; margin-top: 4px; }
dt { color: var(--secondary); font-weight: 400; }
dd { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.full-width { grid-column: 1 / -1; }
@media (max-width: 600px) {
  .history-details > div { grid-template-columns: minmax(0, 1fr); margin-top: 8px; }
}
</style>
