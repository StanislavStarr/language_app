import { fireEvent, render, screen } from '@testing-library/react-native';

import { OptionList } from './option-list';

const OPTIONS = [
  { value: 'a', label: 'Первый', hint: 'Подсказка' },
  { value: 'b', label: 'Второй' },
] as const;

describe('OptionList', () => {
  it('marks only the current value as selected', async () => {
    await render(<OptionList title="Выбор" options={OPTIONS} value="b" onChange={jest.fn()} />);

    expect(screen.getByRole('radio', { name: 'Второй' })).toBeSelected();
    expect(screen.getByRole('radio', { name: 'Первый' })).not.toBeSelected();
  });

  it('reports the pressed option', async () => {
    const onChange = jest.fn();
    await render(<OptionList title="Выбор" options={OPTIONS} value="a" onChange={onChange} />);

    await fireEvent.press(screen.getByRole('radio', { name: 'Второй' }));

    expect(onChange).toHaveBeenCalledWith('b');
  });

  it('ignores presses while disabled', async () => {
    const onChange = jest.fn();
    await render(
      <OptionList title="Выбор" options={OPTIONS} value="a" onChange={onChange} disabled />,
    );

    await fireEvent.press(screen.getByRole('radio', { name: 'Второй' }));

    expect(onChange).not.toHaveBeenCalled();
  });

  it('shows the hint of an option', async () => {
    await render(<OptionList title="Выбор" options={OPTIONS} value="a" onChange={jest.fn()} />);

    expect(screen.getByText('Подсказка')).toBeOnTheScreen();
  });
});
