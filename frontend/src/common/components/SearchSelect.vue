<script setup>
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount, useId, useAttrs } from "vue";
defineOptions({ inheritAttrs: false });
const props = defineProps({
  modelValue: { default: null },
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: "Выберите значение" },
  disabled: Boolean,
  required: Boolean,
  modelModifiers: { type: Object, default: () => ({}) },
});
const emit = defineEmits(["update:modelValue", "change"]);
const attrs = useAttrs();
const uid = useId(), root = ref(), input = ref(), popup = ref();
const opened = ref(false), search = ref(""), active = ref(-1), position = ref({});
const sameValue = (a, b) => a === b || (a != null && b != null && String(a) === String(b));
const selected = computed(() => props.options.find((option) => sameValue(option.value, props.modelValue)));
const matches = computed(() => {
  const query = search.value.trim().toLocaleLowerCase("ru").replaceAll("ё", "е");
  return props.options.filter((option) => String(option.label).toLocaleLowerCase("ru").replaceAll("ё", "е").includes(query));
});
const inputAttrs = computed(() => Object.fromEntries(Object.entries(attrs).filter(([key]) => !["class", "style"].includes(key))));
function updatePosition() {
  if (!opened.value || !root.value) return;
  const rect = root.value.getBoundingClientRect();
  const below = window.innerHeight - rect.bottom - 12;
  const above = below < 180 && rect.top > below;
  const maxHeight = Math.max(80, Math.min(280, above ? rect.top - 12 : below));
  position.value = {
    left: `${Math.max(8, Math.min(rect.left, window.innerWidth - rect.width - 8))}px`,
    width: `${rect.width}px`,
    maxHeight: `${maxHeight}px`,
    ...(above ? { bottom: `${window.innerHeight - rect.top + 4}px` } : { top: `${rect.bottom + 4}px` }),
  };
}
function validate() {
  const valid = !props.required || (selected.value && ![null, undefined, ""].includes(props.modelValue));
  input.value?.setCustomValidity(valid ? "" : "Выберите значение из списка");
}
function open() {
  if (props.disabled || opened.value) return;
  opened.value = true;
  search.value = "";
  active.value = matches.value.findIndex((option) => !option.disabled && sameValue(option.value, props.modelValue));
  if (active.value < 0) active.value = matches.value.findIndex((option) => !option.disabled);
  updatePosition();
  nextTick(() => popup.value?.querySelector(`[data-index="${active.value}"]`)?.scrollIntoView({ block: "nearest" }));
}
function close() {
  opened.value = false;
  search.value = "";
  validate();
}
function choose(option) {
  if (!option || option.disabled) return;
  emit("update:modelValue", option.value);
  emit("change", option.value);
  close();
  nextTick(() => { input.value?.focus(); validate(); });
}
function type(event) {
  open();
  search.value = event.target.value;
  active.value = matches.value.findIndex((option) => !option.disabled);
}
function move(direction) {
  const enabled = matches.value.map((option, index) => option.disabled ? -1 : index).filter((index) => index >= 0);
  if (!enabled.length) return;
  const current = enabled.indexOf(active.value);
  active.value = enabled[(current + direction + enabled.length) % enabled.length];
  nextTick(() => popup.value?.querySelector(`[data-index="${active.value}"]`)?.scrollIntoView({ block: "nearest" }));
}
function keydown(event) {
  if (props.disabled) return;
  if (["ArrowDown", "ArrowUp"].includes(event.key)) {
    event.preventDefault();
    if (!opened.value) open(); else move(event.key === "ArrowDown" ? 1 : -1);
  } else if (event.key === "Enter" && opened.value) {
    event.preventDefault();
    choose(matches.value[active.value]);
  } else if (event.key === "Escape" && opened.value) {
    event.preventDefault();
    event.stopPropagation();
    close();
  } else if (event.key === "Tab") close();
}
function clickAway(event) {
  if (!root.value?.contains(event.target) && !popup.value?.contains(event.target)) close();
}
function blur(event) {
  if (!root.value?.contains(event.relatedTarget) && !popup.value?.contains(event.relatedTarget)) close();
}
watch(() => [props.modelValue, props.required, props.options], () => nextTick(validate), { deep: true });
watch(matches, () => {
  if (active.value >= matches.value.length || matches.value[active.value]?.disabled)
    active.value = matches.value.findIndex(option => !option.disabled);
});
watch(() => props.disabled, (value) => { if (value) close(); });
onMounted(() => {
  validate();
  document.addEventListener("pointerdown", clickAway);
  window.addEventListener("resize", updatePosition);
  window.addEventListener("scroll", updatePosition, true);
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", clickAway);
  window.removeEventListener("resize", updatePosition);
  window.removeEventListener("scroll", updatePosition, true);
});
</script>
<template>
  <div ref="root" class="search-select" :class="[attrs.class, { disabled }]" :style="attrs.style" @keydown="keydown">
    <input ref="input" v-bind="inputAttrs" type="text" role="combobox" autocomplete="off"
      :value="opened ? search : selected?.label || ''"
      :placeholder="opened ? selected?.label || placeholder : placeholder"
      :disabled="disabled" :required="required" :aria-required="required || undefined"
      :aria-expanded="opened" aria-autocomplete="list" aria-haspopup="listbox"
      :aria-controls="`${uid}-list`" :aria-activedescendant="opened && active >= 0 ? `${uid}-option-${active}` : undefined"
      @click="open" @input="type" @blur="blur" />
    <button type="button" class="search-select-toggle" tabindex="-1" :disabled="disabled" aria-hidden="true"
      @mousedown.prevent @click="opened ? close() : (input?.focus(), open())">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m7 10 5 5 5-5" /></svg>
    </button>
    <Teleport to="body">
      <div v-if="opened" ref="popup" :id="`${uid}-list`" class="search-select-options" role="listbox" :style="position"
        :aria-label="attrs['aria-label'] || placeholder" @mousedown.prevent>
        <div v-for="(option, index) in matches" :id="`${uid}-option-${index}`" :key="String(option.value)" :data-index="index"
          role="option" :aria-selected="sameValue(option.value, modelValue)" :aria-disabled="option.disabled || undefined"
          :class="{ highlighted: index === active, selected: sameValue(option.value, modelValue), disabled: option.disabled }"
          @mousemove="active = index" @click="choose(option)">{{ option.label }}</div>
        <p v-if="!matches.length" class="search-select-empty">Ничего не найдено</p>
      </div>
    </Teleport>
  </div>
</template>
<style scoped>
.search-select { position: relative; min-width: 0; width: 100%; }
.search-select input { width: 100%; padding-right: 36px; cursor: pointer; }
.search-select input[aria-expanded="true"] { cursor: text; }
.search-select-toggle { position: absolute; right: 2px; top: 2px; bottom: 2px; width: 32px; min-height: 0; padding: 0; border: 0; background: transparent; color: var(--muted); display: grid; place-items: center; }
.search-select-toggle svg { width: 18px; height: 18px; }
.search-select-options { position: fixed; z-index: 10000; overflow-y: auto; overscroll-behavior: contain; padding: 4px; background: var(--card, #fff); color: var(--text, #171717); border: 1px solid var(--border, #ddd); border-radius: 8px; box-shadow: 0 8px 24px #00000012; font: 14px/20px "Segoe UI", system-ui, sans-serif; }
.search-select-options [role="option"] { padding: 8px 12px; min-height: 36px; border-radius: 4px; cursor: pointer; overflow-wrap: anywhere; white-space: pre-wrap; }
.search-select-options .selected { font-weight: 500; color: var(--accent, #6550b5); }
.search-select-options .highlighted { background: var(--inset, #f4f4f5); }
.search-select-options .disabled { opacity: .5; cursor: default; }
.search-select-empty { color: var(--muted); margin: 0; padding: 12px; }
</style>
