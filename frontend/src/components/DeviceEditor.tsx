import { PlusOutlined } from "@ant-design/icons";
import { Button, Col, Divider, Form, Input, InputNumber, Row, Segmented, Select, Switch } from "antd";
import type { FormInstance } from "antd";
import type { DeviceConfig } from "../api/client";
import type { Device } from "../api/mappers";
import { deviceDefaults } from "./formDefaults";

type DeviceEditorProps = {
  form: FormInstance<DeviceConfig>;
  editing: Device | null;
  onSubmit: () => void | Promise<void>;
};

export function DeviceEditor({ form, editing, onSubmit }: DeviceEditorProps) {
  const profile = Form.useWatch("check_profile", form) ?? "full_stack";
  const isFullStack = profile === "full_stack";
  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={deviceDefaults}
      onFinish={onSubmit}
    >
      <Form.Item
        label="設備名稱"
        name="name"
        rules={[{ required: true, message: "請輸入設備名稱" }]}
      >
        <Input placeholder="例如 PLC-01" />
      </Form.Item>
      <Form.Item label="預設檢查流程" name="check_profile">
        <Segmented
          block
          options={[
            { value: "ping", label: "Ping" },
            { value: "ping_tcp", label: "Ping + TCP" },
            { value: "full_stack", label: "完整檢查" },
          ]}
        />
      </Form.Item>
      <Row gutter={12}>
        <Col span={15}>
          <Form.Item
            label="IP 位址"
            name="ip"
            rules={[
              { required: true, message: "請輸入 IP 位址" },
              {
                pattern:
                  /^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$/,
                message: "IP 格式不正確",
              },
            ]}
          >
            <Input placeholder="192.168.0.50" />
          </Form.Item>
        </Col>
        {isFullStack && <Col span={9}>
          <Form.Item label="Port" name="port">
            <InputNumber min={1} max={65535} style={{ width: "100%" }} />
          </Form.Item>
        </Col>}
      </Row>
      {profile === "ping_tcp" && (
        <Form.Item label="TCP 服務 Port" name="tcp_port" rules={[{ required: true, message: "Ping + TCP 必須指定 TCP Port" }]}>
          <InputNumber min={1} max={65535} style={{ width: "100%" }} />
        </Form.Item>
      )}
      {isFullStack && <>
      <Row gutter={12}>
        <Col span={12}>
          <Form.Item label="Unit ID" name="unit_id">
            <InputNumber min={0} max={247} style={{ width: "100%" }} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item label="功能碼" name="function">
            <Select
              options={[
                { value: "01", label: "01 · Coils" },
                { value: "02", label: "02 · Discrete Inputs" },
                { value: "03", label: "03 · Holding Registers" },
                { value: "04", label: "04 · Input Registers" },
              ]}
            />
          </Form.Item>
        </Col>
      </Row>
      <Row gutter={12}>
        <Col span={14}>
          <Form.Item label="起始位址" name="address">
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
        </Col>
        <Col span={10}>
          <Form.Item label="讀取數量" name="quantity">
            <InputNumber min={1} max={2000} style={{ width: "100%" }} />
          </Form.Item>
        </Col>
      </Row>
      </>}
      <Divider />
      {isFullStack && <Row gutter={12}>
        <Col span={12}>
          <Form.Item label="連線逾時 (ms)" name="connect_timeout_ms">
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item label="回應逾時 (ms)" name="response_timeout_ms">
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
        </Col>
      </Row>}
      {isFullStack && <Row gutter={12}>
        <Col span={12}>
          <Form.Item label="輪詢週期 (ms)" name="scan_rate_ms">
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item label="設備間隔 (ms)" name="delay_between_polls_ms">
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
        </Col>
      </Row>}
      <Form.Item label="啟用設備檢查" name="enabled" valuePropName="checked">
        <Switch />
      </Form.Item>
      <Button block type="primary" htmlType="submit" icon={<PlusOutlined />}>
        {editing ? "儲存連線設定" : "儲存連線設定"}
      </Button>
    </Form>
  );
}
